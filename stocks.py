#!/usr/bin/env python3

import pandas as pd
import numpy as np
from tabulate import tabulate
import datetime
import json
import argparse
import os
from fmv import FMV
from trans import TDTransactionsJSON
from typing import Tuple

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

    df = df.copy()
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

    buys = df[df['qty'] > 0].sort_values(by='date').copy()
    sales = df[df['qty'] < 0].sort_values(by='date').copy()

    dfr = pd.DataFrame(columns=['symbol', 'qty', 'open_date', 'open_price', 'open_price_nok', 'close_date',
                                'close_price', 'tax_deduction', 'idx'])

    for idx, row in sales.iterrows():
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
                                           row['price'], brow['tax_deduction'], brow['idx'] ]
            if to_sell == 0:
                break
    return dfr
            
def gains(df, tax_deductions):
    f = FMV()
    if len(df) == 0:
        return None
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

    dfd = dfd.reset_index()
    dft = dft.reset_index()
    dfd['tax'] = dft.tax

    f = FMV()
    dfd['usdnok'] = dfd.apply(lambda x: f.get_currency('USD', x['date']), axis=1)
    dfd['divnok'] = dfd['dividend'] * dfd['usdnok']
    dfd['taxnok'] = dfd['tax'] * dfd['usdnok']
    dfd['adjdivnok'] = 0

    for idx, row in dfd.iterrows():
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
    #df = df[(df['type'] == 'JOURNAL') & (dfo['description'] == "W-8 WITHHOLDING")].sort_values(by='transactionDate')
    print('CASH\n', df)
    
    # Transfers
    dft = df[df.type == 'ELECTRONIC_FUND']

    # Cash
    dfc = df[df.type == 'RECEIVE_AND_DELIVER']
    # Transfer is a sell of USD med inngangsverdi
    # Match up with sale?
    # A sale should have added up to the cash account
    # A manual match iup with what has been received.
    print('TRANSFERS\n', dft)

    print('CASH\n', dfc['transactionItem.amount'])
    
    ### 56330.26 => 483006.11NOK
    
def annual_report(year, td):
    tax_deductions = td.trades()[['tax_deduction', 'idx']].set_index('idx')

    # Dividends
    d, tax_deductions = dividends(td.trades(), td.dividends(), td.tax(), tax_deductions)
    if d is not None:
        print('\nDIVIDENDS:\n==========')
        print(tabulate(d, headers='keys', tablefmt='pretty', showindex='False', floatfmt='.2f'))
        print(tabulate(d.groupby(['symbol'])[['dividend', 'divnok', 'adjdivnok', 'tax', 'taxnok']].sum(), headers='keys',tablefmt='pretty'))

    # Gains
    s = sales(td.trades())
    if not s.empty:
        print('\nSALES:\n======')
        print(tabulate(s, headers='keys', tablefmt='pretty', showindex='False', floatfmt='.2f'))

        print('\nGAINS:\n======')
        g, tax_deductions = gains(s, tax_deductions)
        if g is not None:
            print(tabulate(g, headers='keys', tablefmt='pretty', showindex='False', floatfmt='.2f'))
        
    b = balance(td.trades())

    # TODO: Make this configurable
    # Must be called after dividends and sales are done
    # Add tax deductions for next year
    h = holdings_to_file(b, tax_deductions, f'data/holdings-{str(year)}.json', year)
    
    pd.options.display.float_format = '{:.2f}'.format
    print(f'HOLDINGS {year}:\n==========')
    print(tabulate(h, headers='keys', tablefmt='pretty', showindex='False', floatfmt='.2f'))

    # Wealth
    r = holdings(b, year)
    print('\nWEALTH:\n========')
    print(tabulate(r, headers='keys', tablefmt='pretty', showindex='False', floatfmt='.2f'))

    '''
    # # Cash transfers, exchange rate gains/losses
    # c = cash(dfo)
    '''

def get_arguments():
    parser = argparse.ArgumentParser(description='Tax Calculator.')
    parser.add_argument('year', type=str,
                        help='Which year(s) to calculate tax for')
    parser.add_argument('-t', '--transactions', help='Per trader transaction file-prefix')
    parser.add_argument('--report', type=str, help='Report type')

    return parser.parse_args()


def main():
    # Get arguments
    args = get_arguments()

    years = args.year.split('-')
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
        td = TDTransactionsJSON(args.transactions+f'-{year}.json', prev_holdings, year)

        # Calculate this year's taxes
        annual_report(year, td)


if __name__ == '__main__':
    main()



#################################################
## Alpha Vantage key: ZVEI7IEOGF4ET67O


### TODO set inngangsveriden i NOK for nye assets, manual inngangsverdi
### TODO Schwab reporter
### TODO Cash. Treat cash like any other symbol. A class that maintains the balance dataframe???
### TODO Specify which importer to use with which file
### TODO Support reading from multiple transactions in one go?
###      --transactions=td-json:<filename> --transactions=schwab:<filename> --holdings=data/holdings-2021.json --year=2021 
### TODO Sell: should result in a cash buy transaction
