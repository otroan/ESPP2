#!/usr/bin/env python3

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

class Cash():
    ''' Cash balance.'''
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            print('Creating the object')
            cls._instance = super(Cash, cls).__new__(cls)
            # Put any initialization here.
            cls.df = pd.DataFrame(columns=['type', 'symbol', 'date', 'qty', 'price_nok'])
        return cls._instance

    def debit(self, date, qty, price_nok):
        self.df.loc[len(self.df.index)] = 'BUY', 'USD', date, qty, price_nok

    def credit(self, date, qty, price_nok):
        self.df.loc[len(self.df.index)] = 'SELL', 'USD', date, qty, price_nok

    def withdrawal(self, date, qty, price_nok):
        self.df.loc[len(self.df.index)] = 'WIRE', 'USD', date, qty, price_nok

    def process(self):
        # import IPython
        # IPython.embed()
        # self.df.sort_values(by='date', inplace=True)
        
        buys = self.df[self.df.type == 'BUY'].sort_values(by='date')
        buys['idx'] = 0
        sale = self.df[self.df.type == 'SELL'].sort_values(by='date')
        df = self.df.copy()
        dfr = pd.DataFrame(columns=['symbol', 'qty', 'open_date', 'open_price', 'close_date',
                                    'close_price',  'sales_idx', 'idx'])

        for si, sr in sale.iterrows():
            to_sell = abs(sr.qty)
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
                    print('SOLD', br)
                    dfr.loc[len(dfr.index)] = [sr['symbol'], no, br['date'],  br['price_nok'], sr['date'],
                                             sr['price_nok'], si, bi ]
                if to_sell == 0:
                    break
                
        f = FMV()
        if len(dfr) == 0:
            return None

        #df['usdnok_close'] = df.apply(lambda x: f.get_currency('USD', x.close_date), axis=1)
        
        def g(row):
            gain = row.close_price - row.open_price
            return gain * row.qty
        dfr['total_gain_nok'] = dfr.apply(g, axis=1)
        return dfr
 
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
    return df.groupby(['symbol'], as_index=False)\
        .apply(fifo) \
        .drop(['CS', 'PN'], axis=1) \
        .reset_index(drop=True)

def balance(df):
    ''' Active balance by end of year report '''
    f = FMV()
    df = df.copy()
    #df['price_nok'] = df.apply(lambda row: (row['price'] * f.get_currency('USD', row['date'])), axis=1)
    return active_balance(df)

def balance_by_symbol_and_date(df, symbol, date):
    ''' Active balance for a symbol up to a given date '''
    f = FMV()

    df = df.copy() # Needed?
    df = df[(df.symbol == symbol) & (df.date <= date)]
    if df.empty:
        return df

    # TODO: Move this someplace better
    #df['price_nok'] = df.apply(lambda row: (row['price'] * f.get_currency('USD', row['date'])), axis=1)

    return active_balance(df)

def holdings(df, year):
    '''Calculate end of year wealth'''

    f = FMV() ### Need a singleton of this one
    endofyear = str(year) + '-12-31'
    usdnok = f.get_currency('USD', endofyear)   # Handle stocks not in USD?
    r = df.groupby('symbol', as_index=False)['qty'].sum()
    r['Close'] = r.apply (lambda row: f[row['symbol'], endofyear], axis=1)
    r['CapitalUSD'] = r.apply (lambda row: row['Close'] * row['qty'], axis=1)
    r['CapitalNOK'] = r.apply (lambda row: row['CapitalUSD'] * usdnok, axis=1)

    return r

def holdings_to_file(df, tax_deductions, filename, year):
    '''Write end of year holdings to file'''
    df = df.copy()
    # Add this years skjermingsfradrag
    with open('taxdata.json', 'r') as jf:
        taxdata = json.load(jf)
    tax_deduction_rate = taxdata['tax_deduction_rates'][str(year)][0]
    df = df.set_index('idx')
    tax_deductions = tax_deductions[tax_deductions.index.isin(df.index)]
    df['tax_deduction'] = tax_deductions

    def t(current_deduction, price_nok):
        return current_deduction + (price_nok * tax_deduction_rate)/100

    df['tax_deduction'] = df.apply (lambda row: t(row['tax_deduction'], row['price_nok']), axis=1)
    df['date'] = df['date'].apply(lambda x: x.strftime('%Y-%m-%d %R%z'))

    with open(filename, 'w') as f:
        json.dump(df.to_dict('records'), f, indent=4)
    return df

def sales(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = Cash()
    f = FMV()
    buys = df[df['qty'] > 0].sort_values(by='date')
    buys = buys.copy()
    sales = df[df['qty'] < 0].sort_values(by='date').copy()

    dfr = pd.DataFrame(columns=['symbol', 'qty', 'open_date', 'open_price', 'open_price_nok', 'close_date',
                                'close_price', 'tax_deduction', 'sales_idx', 'idx'])

    for idx, row in sales.iterrows():
        # Buying USD in the cash account
        c.debit(row['date'], row['cost'], f.get_currency('USD', row['date']))
        to_sell = abs(row['qty'])
        for bidx, brow in buys[buys['symbol'] == row['symbol']].iterrows():
            if brow['qty'] >= to_sell:
                buys['qty'].loc[bidx] -= to_sell
                no = to_sell
                to_sell = 0
            else:
                to_sell -= brow['qty']
                no = brow['qty']
                buys['qty'].loc[bidx] = 0
            if no > 0:
                dfr.loc[len(dfr.index)] = [row['symbol'], no, brow['date'], brow['price'], brow['price_nok'], row['date'],
                                           row['price'], brow['tax_deduction'], idx, brow['idx'] ]
            if to_sell == 0:
                break
    return dfr
            
def gains(df, tax_deductions):
    f = FMV()
    if len(df) == 0:
        return None
    df = df.copy()
    df['usdnok_close'] = df.apply(lambda x: f.get_currency('USD', x.close_date), axis=1)
    
    def g(row):
        gain = (row.close_price * row.usdnok_close) - row.open_price_nok
        # The tax deduction can not be used to increase losses, only lessen gains
        if gain > 0:
            gain -= tax_deductions.loc[row.idx].tax_deduction
            if gain < 0:
                gain = 0
        return gain * row.qty
    df['total_gain_nok'] = df.apply(g, axis=1)
    
    # TODO: Do this in formatter
    df['open_date'] = pd.to_datetime(df['open_date']).dt.date
    df['close_date'] = pd.to_datetime(df['close_date']).dt.date

    return df, tax_deductions

def dividends(df, df_dividends, df_tax, td):
    ''' Calculate dividends and tax. Because of the tax deduction this must run before the sales gains calculation'''

    dfd = df_dividends.copy()
    dft = df_tax.copy()
    if dfd.empty and dft.empty:
        return None, td
    c = Cash()

    dfd = dfd.reset_index()
    dft = dft.reset_index()
    dfd['tax'] = dft.tax

    f = FMV()
    dfd['usdnok'] = dfd.apply(lambda x: f.get_currency('USD', x['date']), axis=1)
    dfd['divnok'] = dfd['dividend'] * dfd['usdnok']
    dfd['taxnok'] = dfd['tax'] * dfd['usdnok']
    dfd['adjdivnok'] = 0

    for idx, row in dfd.iterrows():
        c.debit(row.date, row.dividend, row.usdnok)
        c.credit(row.date, row.tax, row.usdnok)
        b = balance_by_symbol_and_date(df, row.symbol, row.date)
        if b.empty:
            print('*** Empty balance for: ', row)
            continue
        dps = (row['divnok'] / b.qty.sum())
        dividend = row['divnok']
        for bidx, brow in b.iterrows():
            i = brow.idx
            if td['tax_deduction'].loc[i] == 0 or np.isnan(td['tax_deduction'].loc[i]):
                continue
            if td['tax_deduction'].loc[i] >= dps:
                td['tax_deduction'].loc[i] -= dps
                dividend -= (dps * brow.qty)
            else:
                dividend -= (td['tax_deduction'].loc[i] * brow.qty)
                td['tax_deduction'].loc[i] = 0
        dfd['adjdivnok'].iloc[idx] = dividend
    return dfd, td

def cash(df):
    print('CASH CASH', df)
    c = Cash()
    
    for i, r in df.iterrows():
        print('WWW', r)
        c.withdrawal(r['date'], r['cash'], 483006.11/abs(r['cash']))
    print('CASH STATUS', c.process())


    ### 56330.26 => 483006.11NOK
    
def annual_tax(year, td):
    tax_deductions = td.trades()[['tax_deduction', 'idx']].set_index('idx')

    # Dividends
    d, tax_deductions = dividends(td.trades(), td.dividends(), td.tax(), tax_deductions)

    # Gains
    s = sales(td.trades())
    if not s.empty:
        g, tax_deductions = gains(s, tax_deductions)
        
    b = balance(td.trades())

    # Wealth
    r = holdings(b, year)

    # Cash transfers, exchange rate gains/losses
    c = cash(td.cash())

    return {'dividends': d, 'sales': s, 'gains': g, 'wealth': r,
            'tax_deductions': tax_deductions,
            'balance': b}

def save_holdings_to_file(balance):
    h = holdings_to_file(balance, tax_deductions, f'data/holdings-{str(year)}.json', year)
    

def annual_report(r):
    if r['dividends'] is not None:
        print('\nDIVIDENDS:\n==========')
        print(tabulate(r['dividends'], headers='keys', tablefmt='pretty', showindex='False', floatfmt='.2f'))
        print(tabulate(r['dividends'].groupby(['symbol'])[['dividend', 'divnok', 'adjdivnok', 'tax', 'taxnok']].sum(), headers='keys',tablefmt='pretty'))

    # Gains
    if not r['sales'].empty:
        print('\nSALES:\n======')
        print(tabulate(r['sales'], headers='keys', tablefmt='pretty', showindex='False', floatfmt='.2f'))

        print('\nGAINS:\n======')
        if r['gains'] is not None:
            print(tabulate(r['gains'], headers='keys', tablefmt='pretty', showindex='False', floatfmt='.2f'))
        
    # print(f'BALANCE:\n==========')
    # print(tabulate(r['balance'], headers='keys', tablefmt='pretty', showindex='False', floatfmt='.2f'))

    # Wealth
    print('\nWEALTH:\n========')
    print(tabulate(r['wealth'], headers='keys', tablefmt='pretty', showindex='False', floatfmt='.2f'))

    '''
    # # Cash transfers, exchange rate gains/losses
    # c = cash(dfo)
    '''

def get_arguments():
    parser = argparse.ArgumentParser(description='ESPP 2Tax Calculator.')
    parser.add_argument('year', type=str,
                        help='Which year(s) to calculate tax for')
    parser.add_argument('--transactions', help='Per trader transaction file-prefix')
    parser.add_argument('--report', type=str, help='Report type')
    parser.add_argument('--generate-holdings', type=str, help='Holdings file for range of years')
    parser.add_argument('--holdings', type=str, help='Holdings file for selected year')

    return parser.parse_args()

###
### Command line interface
### Tax report, one year at the time.
###    Input: transaction files, previous year holdings
### Generate holdings files. Range of years.

### Prefix files with {format}
### Support glob?


def main():
    # Get arguments
    args = get_arguments()
    years = args.year.split('-')

    if args.generate_holdings:
        start = int(years[0])
        if len(years ) == 1:
            end = start
        else:
            end = int(years[1])
        for year in range(start, end+1):
            print(f'{year} TAX REPORT')
            # Get holdings from previous year
            prev_holdings = f'data/holdings-{str(year - 1)}.json'    
            # Read in transaction file and concatenate with previous year
    else:
        year = int(years[0])
        try:
            f, n = args.transactions.split(':')
        except ValueError:
            sys.exit('Specify format of transaction file <format>:<transactionfile>')
        print('F N', f, n)
        t = read_transactions(f, n, args.holdings, year)

        # Calculate this year's taxes
        r = annual_tax(year, t)

        # Print report
        annual_report(r)
        
        
        c = Cash()
        print('CASH HOLDINGS:\n', c.df)


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
