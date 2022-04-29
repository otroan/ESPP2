#!/usr/bin/env python3

from cmath import nan
import sys
import pandas as pd
import numpy as np
from tabulate import tabulate
import datetime
import json
import argparse
import os
from fmv import FMV
from trans import read_transactions
from typing import Tuple
import logging
import IPython

class Cash():
    ''' Cash balance.
    1) Cash USD Brokerage (per valuta)
    2) Hjemmebeholdning av valuta  (valutatrans)
    3) NOK hjemme
    '''
    _instance = None

    def __new__(cls, wire_filename=None):
        if cls._instance is None:
            cls._instance = super(Cash, cls).__new__(cls)
            # Put any initialization here.
            cls.df = pd.DataFrame(columns=['type', 'symbol', 'date', 'qty', 'usdnok', 'amount_nok'])
            cls.wire_filename = wire_filename
        return cls._instance

    def debit(self, date, qty, usdnok):
        self.df.loc[len(self.df.index)] = 'BUY', 'USD', date, qty, usdnok, np.nan

    def credit(self, date, qty):
        ''' TODO: Return usdnok rate for the item credited '''
        self.df.loc[len(self.df.index)] = 'SELL', 'USD', date, qty, np.nan, np.nan

    def withdrawal(self, date, qty, usdnok, amount_nok):
        self.df.loc[len(self.df.index)] = 'WIRE', 'USD', date, qty, usdnok, amount_nok

    def wire(self, wires):
        '''Merge wires rows with received NOK USD table'''

        ### Separate directory for each
        ### 
        logging.info(f'Reading wire received from {self.wire_filename}')
        if not self.wire_filename or not os.path.isfile(self.wire_filename):
            logging.warning(f'No wire received file: {self.wire_filename}')
            return

        dfr = pd.read_json(self.wire_filename)

        w = wires[['type', 'symbol', 'date', 'amount']].copy()
        w.sort_values(by='date', inplace=True)
        w.reset_index(inplace=True)

        if len(w) != len(dfr):
            raise Exception(f'Number of wires sent is different from received {w}\n{dfr}')
        dfr['date'] = pd.to_datetime(dfr['date'], utc=True)
        dfr.sort_values(by='date', inplace=True)
        dfr.reset_index(inplace=True)
        
        w['received_nok'] = dfr['amount']
        w['received_date'] = dfr['date']
        w['usdnok'] = abs(w['received_nok'] / w['amount'])

        w['type'] = 'WIRE'
        
        for i,r in w.iterrows():
            self.withdrawal(r.date, r.amount, r.usdnok, r.received_nok)

        # TODO: Verify USD fields
        # TODO: Raise exception if wire or received fields don't match
        # IPython.embed()
        return w

    def process(self):
        ''' Process the cash account.'''

        sale = self.df[self.df.type.isin(['WIRE', 'SELL'])].sort_values(by='date')
        df = self.df.copy()
        dfr = pd.DataFrame(columns=['symbol', 'qty', 'open_date', 'open_price', 'close_date',
                                    'close_price',  'sales_idx', 'idx'])

        for si, sr in sale.iterrows():
            to_sell = abs(sr.qty)
            buys = df[df.type == 'BUY'].sort_values(by='date')
            for bi, br in buys.iterrows():
                if br.qty >= to_sell:
                    df.loc[bi, 'qty'] -= to_sell
                    no = to_sell
                    to_sell = 0
                else:
                    to_sell -= br.qty
                    no = br.qty
                    df.loc[bi, 'qty'] = 0
                if no > 0:
                    dfr.loc[len(dfr.index)] = [sr['symbol'], no, br['date'],  br['usdnok'], sr['date'],
                                             sr['usdnok'], si, bi ]
                if to_sell == 0:
                    break
                
        if len(dfr) == 0:
            return None
       
        def g(row):
            gain = row.close_price - row.open_price
            return gain * row.qty
        dfr['total_gain_nok'] = dfr.apply(g, axis=1)

        return dfr

class Transactions():
    def __init__(self, transactions, year, outholdings = None):
        self.transactions = transactions
        self.year = year
        self.outholdings = outholdings
        
        ## TODO: Delete this?
        self.tax_deductions = transactions.trades()[['tax_deduction', 'idx']].set_index('idx')

        # Add this years tax deduction
        with open('taxdata.json', 'r') as jf:
            taxdata = json.load(jf)
        self.tax_deduction_rate = taxdata['tax_deduction_rates'][str(year)][0]
        self.tax_deduction_rate_prev_year = taxdata['tax_deduction_rates'][str(year-1)][0]

    def buys(self):
        '''
        Process this year's buy transactions.
        A buy credits cash from the cash account in exchange for shares.
        The cost basis for the USD is provided in NOK.
        Calculates the cost basis for the shares.
        '''
        c = Cash()
        f = FMV()
        dfo = self.transactions.trades()
        df = dfo[(dfo.type.isin(['BUY', 'DEPOSIT'])) & (dfo.date.dt.year == self.year)]

        #### TODO TODO TODO ####
        #### Setting inngangsverdi bankrate
        for i, r in df.iterrows():
            #raise Exception('NEED TO DO 2 passes to calculate usdnok')
            if r.type == 'BUY':
                c.credit(r.date, r.amount)
            elif r.type == 'DEPOSIT' and r.DESCRIPTION == 'Div Reinv':
                c.credit(r.date, -1 * r.price * r.qty)
            # TODO: Figure out the real purchase price
            dfo.loc[i, 'price_nok']  = r.price * f.get_currency('USD', r.date)

            # If the purchase date of the ESPP is the previous year, add tax deduction
            # TODO: Make this configurable. Only applies to Schwab ESPP
            try:
                if r['DESCRIPTION'] == 'ESPP':
                    subdata = r['subdata']
                    purchase_date = pd.to_datetime(subdata[0]['PURCHASE DATE'], utc=True)
                    if purchase_date.year + 1 == self.year:
                        # Adding tax deduction for purchase_year to this entry
                        dfo.loc[i, 'tax_deduction'] += self.tax_deduction_rate_prev_year * dfo.loc[i, 'price_nok'] / 100
            except KeyError:
                pass                    

        return dfo[(dfo.type.isin(['BUY', 'DEPOSIT'])) & (dfo.date.dt.year == self.year)]

    def sales(self, df):
        c = Cash()
        f = FMV() 

        sale = df[df.type == 'SELL'].sort_values(by='date')
        sale['price_nok'] = sale.apply(lambda r: (r.price * f.get_currency('USD', r.date)), axis=1)

        # Take cost basis in NOK via cash account
        sd = {}

        for si, sr in sale.iterrows():
            # Buying USD in the cash account
            c.debit(sr['date'], sr['amount'], f.get_currency('USD', sr['date']))
            to_sell = abs(sr.qty)
            buys = df[df.type.isin(['BUY', 'DEPOSIT'])].sort_values(by='date')
            for bi, br in buys[buys.symbol == sr.symbol].iterrows():
                if br.qty >= to_sell:
                    df.loc[bi, 'qty'] -= to_sell
                    no = to_sell
                    to_sell = 0
                else:
                    to_sell -= br.qty
                    no = br.qty
                    df.loc[bi, 'qty'] = 0
                if no > 0:
                    d = {'no': no, 'sale_price': sr.price, 'sale_price_nok': sr.price_nok,
                         'sale_date': sr.date, 'sale_record': si}
                    i = bi
                    if i not in sd:
                        sd[i] = [d]
                    else:
                        sd[i].append(d)
                        
                if to_sell == 0:
                    break
        if to_sell > 0:
            raise Exception(f'Selling more shares than we have {to_sell}')
        if len(sd) == 0:
            return None

        df['gain_nok'] = 0
        df['sale'] = 0

        sale_report = []
        for k,v in sd.items():
            r = {}
            r = df.loc[k]
            gain = 0
            for s in v:
                assert r.price_nok > 0
                gain_ps = s['sale_price_nok'] - r.price_nok
                gain_ps_pre = gain_ps                
                if df.loc[k, 'tax_deduction'] > 0:
                    print('TAX DEDUCTION', df.loc[k, 'tax_deduction'])
                if df.loc[k, 'tax_deduction'] > 0 and gain_ps < 0:
                    print('WASTED TAX DEDUCTION', df.loc[k, 'tax_deduction_used'], gain_ps)
                if gain_ps > 0:
                    gain_ps -= df.loc[k, 'tax_deduction']
                    if gain_ps < 0:
                        gain_ps = 0
                gain += (gain_ps * s['no'])
                s['gain_nok'] = gain_ps * s['no']
                s['tax_deduction_used'] = gain_ps_pre - gain_ps
            df.loc[k, 'gain_nok'] = gain
            df.loc[k, 'sale'] = str(v)
            r = df.loc[k][['symbol', 'date', 'price', 'price_nok', 'tax_deduction_used', 'gain_nok']].to_dict()
            r['sale'] = v
            sale_report.append(r)
        #IPython.embed()

        return df, sd, sale_report

    def dividends(self):
        ''' Calculate dividends and tax. Because of the tax deduction this must run before the sales gains calculation'''
        c = Cash()
        f = FMV()

        dfd = self.transactions.dividends().copy()
        dft = self.transactions.tax().copy()
        df = self.transactions.trades().copy()
        if dfd.empty and dft.empty:
            return None

        dfd = dfd.reset_index()
        dft = dft.reset_index()
        dfd['tax'] = dft.amount

        dfd['usdnok'] = dfd.apply(lambda x: f.get_currency('USD', x['date']), axis=1)
        dfd['divnok'] = dfd['amount'] * dfd['usdnok']
        dfd['taxnok'] = dfd['tax'] * dfd['usdnok']
        holdings = {}

        # Attach dividend per share to all held records
        for idx, row in dfd.iterrows():
            c.debit(row.date, row.amount, row.usdnok)
            c.credit(row.date, row.tax)
            b = balance_by_symbol_and_date(df, row.symbol, row.date)
            # IPython.embed()
            if b.empty:
                print('*** Empty balance for: ', row)
                continue
            dps = (row['divnok'] / b.qty.sum())
            for bidx, brow in b.iterrows():
                i = bidx
                d = {'no': brow.qty, 'dps': dps}
                if i not in holdings:
                    holdings[i] = [d]
                else:
                    holdings[i].append(d)
                    
            #dfd.loc[idx, 'adjdivnok'] = dividend

        # Deal with tax deduction on dividends
        df = df[['type', 'symbol', 'date', 'qty', 'price', 'amount', 'price_nok', 'tax_deduction']]
        df['tax_deduction_used'] = 0
        df['dps'] = 0
        for k,v in holdings.items():
            tax_ded_used = 0
            dps = 0
            for d in v:
                dps += d['dps']
                if df.loc[k, 'tax_deduction'] > d['dps']:
                    tax_ded_used += d['dps'] * d['no']
                    df.loc[k, 'tax_deduction'] -= d['dps']
                elif df.loc[k, 'tax_deduction'] > 0:
                    tax_ded_used += df.loc[k, 'tax_deduction'] * d['no']
                    df.loc[k, 'tax_deduction'] = 0
            df.loc[k, 'tax_deduction_used'] = tax_ded_used
            df.loc[k, 'dps'] = dps
        # IPython.embed()
        return dfd, df, holdings

    def holdings_summary(self):
        '''Calculate end of year assets'''
        df = self.transactions.trades().copy()      
        df = active_balance(df)
          
        f = FMV()
        endofyear = str(self.year) + '-12-31'
        usdnok = f.get_currency('USD', endofyear)
        r = df.groupby('symbol', as_index=False)['qty'].sum()
        r['Close'] = r.apply (lambda row: f[row['symbol'], endofyear], axis=1)
        r['CapitalUSD'] = r.apply (lambda row: row['Close'] * row['qty'], axis=1)
        r['CapitalNOK'] = r.apply (lambda row: row['CapitalUSD'] * usdnok, axis=1)

        return r
    
    def holdings_to_file(self, filename):
        '''Write end of year holdings to file'''
        
        ### TODO: Add cash holdings

        df = self.transactions.trades().copy() 
        df = active_balance(df)
        df = df.set_index('idx')
        tax_deductions = self.tax_deductions[self.tax_deductions.index.isin(df.index)]
        df['tax_deduction'] = tax_deductions

        def t(current_deduction, price_nok):
            return current_deduction + (price_nok * self.tax_deduction_rate)/100

        df['tax_deduction'] = df.apply (lambda row: t(row['tax_deduction'], row['price_nok']), axis=1)
        df['date'] = df['date'].apply(lambda x: x.strftime('%Y-%m-%d %R%z'))

        # Copy out the fields we need
        h = df[['symbol', 'date', 'qty', 'price', 'amount', 'price_nok', 'tax_deduction']]
        h = h.to_dict('records')
        r = {}
        r['stocks'] = h
        r['cash'] = []
        if filename:
            logging.info(f"Writing holdings to {filename}")
            with open(filename, 'w') as f:
                json.dump(r, f, indent=4)
        return df

    def process(self):
        self.buys_report = self.buys()
        self.dividend_report, self.dividend_report2, d2 = self.dividends()
        self.sales_report, s2, self.sales_report2 = self.sales(self.dividend_report2)
        self.holdings_report = self.holdings_summary()
        self.holdings_eoy = self.holdings_to_file(self.outholdings)

def active_balance(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Given a set of trades using FIFO sell order calculate the final set of stock sets.
    Input: dataframe of trades with columns: Symbol, Open date, Qty, Type (BUY/SELL)
    Returns: dataframe with the ending balance
    '''
    def fifo(dfg):
        try:
            no_sells = abs(dfg[dfg['PN'] == 'N']['CS'].iloc[-1])
        except IndexError:
            no_sells = 0
        try:
            no_buys = abs(dfg[dfg['PN'] == 'P']['CS'].iloc[-1])
        except IndexError:
            no_buys = 0
        if no_sells > no_buys:            
            raise Exception(f'Selling stocks you do not have. {dfg}')
        if dfg[dfg['CS'] < 0]['qty'].count():
            subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
            dfg['qty'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['qty'])
            dfg = dfg[dfg['qty'] > 0]
            if (len(dfg) > 0):
                dfg['qty'].iloc[0] = dfg['CS'].iloc[0] + subT
        return dfg

    df['PN'] = np.where(df['qty'] > 0, 'P', 'N')
    df['CS'] = df.groupby(['symbol', 'PN'])['qty'].cumsum()
    return df.groupby(['symbol'], as_index=False, group_keys=False)\
        .apply(fifo) \
        .drop(['CS', 'PN'], axis=1)
        # .reset_index(drop=True)
        # TODO: CHECK THIS ONE. DO WE NEED 'idx' column

def balance(df):
    ''' Active balance by end of year report '''
    f = FMV()
    #df = df.copy()
    #df['price_nok'] = df.apply(lambda row: (row['price'] * f.get_currency('USD', row['date'])), axis=1)
    return active_balance(df)

def balance_by_symbol_and_date(df, symbol, date):
    ''' Active balance for a symbol up to a given date '''
    f = FMV()

    df = df.copy() # Needed?
    df = df[(df.symbol == symbol) & (df.date <= date)]
    if df.empty:
        return df
    return active_balance(df)

def get_arguments():
    description='''
    ESPP 2 Tax Calculator.
    Calculates Norwegian taxes on US shares. Currently Schwab and TD Ameritrade are supported.
    Input files need to exist in a directory hierarchy as follows.
    In directory given by {prefix}: {year}/{broker}/
    There has to be a transactions.csv file, downloaded from the respective broker.
    In addition there has to be a manually updated file with the wire transactions. In wires.json.
    If this is not the first year, previous EOY holdings must be in {year-1}/{broker}/holdings.json.
    '''
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('year', type=int,
                        help='Which year to calculate tax for')
    #parser.add_argument('--report', type=str, help='Report type')
    parser.add_argument('--prefix', type=str, help='Directory containing the data files')
    parser.add_argument('--gen-holdings', action='store_true', help='Generate EOY holdings file')
    parser.add_argument('--broker', type=str, help='Which broker')
    
    parser.add_argument(
        "-log",
        "--log",
        default="warning",
        help=(
            "Provide logging level. "
            "Example --log debug', default='warning'"),
    ),

    options = parser.parse_args()
    levels = {
        'critical': logging.CRITICAL,
        'error': logging.ERROR,
        'warn': logging.WARNING,
        'warning': logging.WARNING,
        'info': logging.INFO,
        'debug': logging.DEBUG
    }
    level = levels.get(options.log.lower())

    if level is None:
        raise ValueError(
        f"log level given: {options.log}"
        f" -- must be one of: {' | '.join(levels.keys())}")

    logging.basicConfig(level=level)
    logger = logging.getLogger(__name__)

    return parser.parse_args()

def tax_summary(t):
    r = ""

    # Utenlandske aksjer:
    r += '\n# Utenlandske aksjer:\n'

    r += '## Antall aksjer per 31.12 og Formue\n'
    
    # Antall akjser per 31.12
    # Formue
    r += t.holdings_report[['symbol', 'qty', 'CapitalNOK']].to_markdown(index=False)

    # Skattepliktig utbytte
    r += '\n## Skattepliktig utbytte:\n'     
    tax_ded_used = t.sales_report.groupby(['symbol'])['tax_deduction_used'].sum()
    tax_ded_total = t.dividend_report.groupby(['symbol'])[['divnok', 'taxnok']].sum()
    tax_ded_total['tax_deduction_used'] = tax_ded_used
    tax_ded_total['net_dividend_nok'] = tax_ded_total['divnok'] - tax_ded_total['tax_deduction_used']
    r += tax_ded_total['net_dividend_nok'].to_markdown(index=False)    
    r += '\n\n'
 
    # Skattepliktig gevinst
    r += '## Skattepliktig gevinst:\n'    
    totals = {}
    for i in t.sales_report2:
        if not i['symbol'] in totals:
            totals[i['symbol']] = {'no': 0, 'gain': 0, 'tax_ded': 0}
        for j in i['sale']:
            totals[i['symbol']]['no'] += j['no']
            totals[i['symbol']]['gain'] += j['gain_nok']
            totals[i['symbol']]['tax_ded'] += j['tax_deduction_used']

    r += '| symbol | gain/loss nok |\n'
    r += '|---|---|\n'
            
    for k,v in totals.items():
        r += f'|{k}|{v["gain"]:.2f}|\n'

    r += '\n\n'
    
    # Anvendt skjerming
    r += '## Anvendt skjerming:\n'
    r += tax_ded_total[['tax_deduction_used']].to_markdown(index=True)    
    r += '\n\n'
    
    r += '# Fradrag for betalt skatt i utlandet:\n'

    # Inntektsskatt
    # Brutto akjseutbytte
    # Herav skatt på brutto akjseutbytte
    r += '## Inntektsskatt, Brutto akjseutbytte Herav skatt på brutto akjseutbytte:\n'
    r += tax_ded_total[['taxnok', 'divnok', 'taxnok']].to_markdown(index=False)    
    print(f'{r}\n')

def main():
    # Get arguments
    args = get_arguments()

    if not args.prefix:
        sys.exit(-1)

    currentyeardir = f'{args.prefix}/{str(args.year)}/{args.broker}/'
    previousyeardir = f'{args.prefix}/{str(args.year-1)}/{args.broker}/'
    if args.broker == 'schwab':
        f = 'schwab-csv'
    if args.broker == 'tdameritrade':
        # TODO: Add auto-detection of JSON or CSV format
        f = 'td-csv'

    transactionsfile = currentyeardir + 'transactions.csv'
    holdingsfile = previousyeardir + 'holdings.json'
    wirefile = currentyeardir + 'wires.json'

    if args.gen_holdings:
        outholdingsfile = currentyeardir + 'holdings.json'
    else:
        outholdingsfile = None


    t = read_transactions(f, transactionsfile, holdingsfile, args.year)
    c = Cash(wire_filename=wirefile)
    if not t.dfprevh_cash.empty:
        t.dfprevh_cash.apply(lambda x: c.debit(x.date, x.qty, x.price), axis=1)
    
    transactions = Transactions(t, args.year, outholdingsfile)
    transactions.process()

    r = f'# Tax Report {currentyeardir} for {args.broker}\n\n'

    # Holdings at beginning of year
    r += f'## Holdings as of {args.year}-01-01\n'
    r += t.dfprevh[['symbol', 'date', 'qty', 'price', 'price_nok', 'tax_deduction']].to_markdown(index=False)
    r += '\n\n'
    tmp = t.dfprevh
    tmp['total_tax_ded'] = tmp['tax_deduction'] * tmp['qty']
    tmp = t.dfprevh.groupby('symbol', as_index=False)
    # IPython.embed()
    r += tmp[['qty', 'total_tax_ded']].sum().to_markdown(index=False)
    # r += t.dfprevh.groupby('symbol', as_index=False)[['qty', 'tax_deduction'*'qty']].sum().to_markdown(index=False)
    r += '\n\n'

    # Buys / Deposits during year
    r += f'## Buys during the year\n'
    r += transactions.buys_report[['symbol', 'date', 'qty', 'price', 'price_nok']].to_markdown(index=False)
    r += '\n\n'
    r += transactions.buys_report.groupby('symbol', as_index=False)['qty'].sum().to_markdown(index=False)
    r += '\n\n'

    # Sales during year
    # TODO: Move some of this back to the sales function?
    r += f'## Sales during the year\n'
    r += '| symbol | date | price | price nok | sale date | sale price | sale price nok | qty | gain nok | tax ded used |\n'
    r += ':---|---|---|---|---|---|---|---|---|---:|\n'
    totals = {}
    for i in transactions.sales_report2:
        r += f"|{i['symbol']} | {i['date'].strftime('%Y-%m-%d')} | {i['price']} | {i['price_nok']:.2f} |"
        pad = ''
        if not i['symbol'] in totals:
            totals[i['symbol']] = 0
        for j in i['sale']:
            r += f"{pad}{j['sale_date'].strftime('%Y-%m-%d')} | {j['sale_price']:.2f} | {j['sale_price_nok']:.2f} | {j['no']:.2f}|{j['gain_nok']:.2f} | {j['tax_deduction_used']:.2f} |\n"
            pad = '|||||'
            totals[i['symbol']] += j['no']

    r += transactions.sales_report.groupby('symbol', as_index=False)[['qty', 'gain_nok']].sum().to_markdown(index=False)

    r += '### Total sales:\n'
    r += '| symbol | qty |\n'
    r += '|---|---|\n'

    for k,v in totals.items():            
        r += f'|{k}|{v}'

    r += '\n\n'
            
    # Dividends
    r += f'## Dividends\n'
    r += transactions.dividend_report[['symbol', 'date', 'amount', 'divnok', 'tax', 'taxnok']].to_markdown(index=False)
    r += '\n\n'

    # Dividends deduction used
    r += f'## Dividends tax deduction used\n'
    tax_ded_used = transactions.sales_report.groupby(['symbol'])['tax_deduction_used'].sum()
    tax_ded_total = transactions.dividend_report.groupby(['symbol'])[['amount', 'divnok', 'tax', 'taxnok']].sum()

    tax_ded_total['tax_deduction_used'] = tax_ded_used
    r += tax_ded_total.to_markdown(index=False)    
    r += '\n\n'
    
    # Cash and wire transfers
    c = Cash()
    t.fees().apply(lambda x: c.credit(x.date, x.amount), axis=1)
    c.wire(t.cash())
    cdf = Cash().df.sort_values(by='date')
    cdf['date'] = cdf['date'].apply(lambda x: x.strftime('%Y-%m-%d'))

    r += f'## Cash\n'
    r += cdf[['symbol', 'date', 'qty', 'usdnok', 'amount_nok']].to_markdown(index=False)
    r += '\n'
    r += f"|Total||{cdf['qty'].sum():.2f}|||"
    r += '\n\n'
    wires = c.process()
    
    r += f"### Cash total gains: {wires['total_gain_nok'].sum():.2f}"
    r += '\n\n'

    # Holdings at end of year
    r += f'## EOY Holdings\n'
    r += transactions.holdings_eoy[['symbol', 'date', 'qty', 'price', 'price_nok', 'tax_deduction']].to_markdown(index=False)
    r += '\n\n'
    r += transactions.holdings_report.to_markdown(index=False)
    r += '\n\n'

    print(r)
    
    tax_summary(transactions)

if __name__ == '__main__':
    main()


#################################################
## Alpha Vantage key: ZVEI7IEOGF4ET67O


### TODO set inngangsveriden i NOK for nye assets, manual inngangsverdi
### TODO Schwab reporter
### TODO Cash. Treat cash like any other symbol. A class that maintains the balance dataframe???
### TODO Specify which importer to use with which file, TD JSON, TD CSV, Schwab CSV
### TODO Support reading from multiple transactions in one go?
###      --transactions=td-json:<filename> --transactions=schwab:<filename> --holdings=data/holdings-2021.json --year=2021 
### TODO Sell: should result in a cash buy transaction

### TODO: Separate "generate holdings argument"
### TODO: "Reset holdings". Go through all transactions, write holdings file
### TODO: Previous holdings file as cli argument
### TODO: Fees. Search for nearest fee transaction.
### TODO: Rapporter anvendt skjerming


### Per akjsepost. Så vet jeg:
###  - skjermingsfradrag
###  - utbytteutbetalinger
###  - akjser solgt til hvilken salgspris
### Post prosessering for skjermingsfradrag.
###    Hvis tapssalg, bruk skjermingsfradrag på utbytte.
###    Hvis ikke solgt brukt skjermingsfradrag på utbytte
###    Hvis salg med gevinst bruk skjermingsfradrag på salg
### Fix the inde shit

### Summary: Number shares had, bought and sold

## TODO list 21. april
## 1. Skjermingsfradrag for fjorårets ESPP. Men ikke formue.
## 3. Attribute fees to corresponding transactions
## 4. Cash in generated holdings file
## 5. Calculate total available tax deductions at January 1.





