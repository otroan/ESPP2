#!/usr/bin/env python3

import sys
import pandas as pd
import numpy as np
import json
import os
from fmv import FMV

class TDTransactionsJSON():
    def __init__(self, json_file, prev_holdings, year) -> None:
        with open(json_file, 'r') as jf:
                json_data = json.load(jf)
        self.df = pd.json_normalize(json_data)
        self.df_trades = None
        self.df_dividend = None
        self.df_tax = None
        self.df_cash = None
        self.year = year

        # Get holdings from previous year
        dfprevh = None
        if prev_holdings and os.path.isfile(prev_holdings):
            dfprevh = pd.read_json(prev_holdings)
            dfprevh['date'] = pd.to_datetime(dfprevh['date'])
        else:
            print('*** NO PREVIOUS HOLDINGS IS THIS REALLY FIRST YEAR? ***', file=sys.stderr)
        self.dfprevh = dfprevh

    def trades(self):
        # Create trades dataframe
        if self.df_trades is not None:
            return self.df_trades


        ### TODO: Move these to __init__
        tmp = self.df[(self.df.type.isin(['TRADE', 'RECEIVE_AND_DELIVER'])) & (self.df['transactionItem.instrument.assetType'] == 'EQUITY')]
        if len(tmp) == 0:
            self.df_trades = self.dfprevh
            self.df_trades['idx'] = pd.Index(range(len(self.df_trades.index)))
            return self.dfprevh
        df = pd.DataFrame()
        df[['type', 'symbol', 'date',
                'qty', 'price', 'cost', 'amount']] = tmp[['transactionItem.instruction',
                                                                            'transactionItem.instrument.symbol',
                                                                            'transactionDate',
                                                                            'transactionItem.amount',
                                                                            'transactionItem.price',
                                                                            'transactionItem.cost',
                                                                            'netAmount']]
        df['qty'] = np.where(df['type'] == 'SELL', -1 * df['qty'], df['qty'])

        f = FMV()

        # Filter out transactions for given year
        df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'].dt.year == self.year]
        df = df.sort_values(by='date')
        df['price_nok'] = df.apply(lambda row: (row['price'] * f.get_currency('USD', row['date'])), axis=1)
        df['tax_deduction'] = 0

        if self.dfprevh is not None:
            df = pd.concat([self.dfprevh, df])

        df['idx'] = pd.Index(range(len(df.index)))

        self.df_trades = df
        return df

    def dividends(self):
        # Create dividends dataframe
        if self.df_dividend is not None:
            return self.df_dividend

        tmp = self.df[(self.df.type == 'DIVIDEND_OR_INTEREST') & (self.df['transactionItem.instrument.assetType'] == 'EQUITY')].sort_values(by='transactionDate')
        df = pd.DataFrame()
        df[['symbol', 'date', 'dividend']] = tmp[['transactionItem.instrument.symbol',
                                                  'transactionDate',
                                                  'netAmount']]

        # Filter out transactions for given year
        df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'].dt.year == self.year]

        self.df_dividend = df
        return df

    def tax(self):
        # Create taxs dataframe
        if self.df_tax is not None:
            return self.df_tax

        tmp = self.df[(self.df.type == 'JOURNAL') & (self.df.description == 'W-8 WITHHOLDING')].sort_values(by='transactionDate')
        df = pd.DataFrame()
        df[['symbol', 'date', 'tax']] = tmp[['transactionItem.instrument.symbol',
                                             'transactionDate',
                                             'netAmount']]

        # Filter out transactions for given year
        df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'].dt.year == self.year]

        self.df_tax = df
        return df

    def cash(self):
        '''
        Create cash transaction dataframe.
        Dividends, tax, interest and wire transfers. Sales and buys are handled separately.
        '''
        if self.df_cash is not None:
            return self.df_cash

        tmp = self.df[self.df.type == 'ELECTRONIC_FUND']
        df = pd.DataFrame()
        df[['date', 'cash']] = tmp[['transactionDate', 'netAmount']]

        # Filter out transactions for given year
        df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'].dt.year == self.year]

        self.df_cash = df
        return df

def description_to_type(value):
    print('VALUE', value, type(value))
    if value.startswith('Bought') or value.startswith('TRANSFER OF SECURITY'):
        return 'BUY'
    if value.startswith('Sold'):
        return 'SELL'
    if value.startswith('ORDINARY DIVIDEND'):
        return 'DIVIDEND'
    if value.startswith('W-8 WITHHOLDING'):
        return 'TAX'
    if value.startswith('CLIENT REQUESTED ELECTRONIC FUNDING DISBURSEMENT'):
        return 'WIRE'
    return value


class TDTransactionsCSV():
    def __init__(self, csv_file, prev_holdings, year) -> None:
        df = pd.read_csv(csv_file, converters={'DESCRIPTION': description_to_type})
        self.df_trades = None
        self.df_dividend = None
        self.df_tax = None
        self.year = year

        df = df.rename(columns={'DATE': 'date',
                                'TRANSACTION ID': 'transaction_id',
                                'DESCRIPTION': 'type',
                                'SYMBOL': 'symbol',
                                'QUANTITY': 'qty',
                                'PRICE': 'price',
                                'FUND REDEMPTION FEE': 'fee1',
                                'SHORT-TERM RDM FEE': 'rdm',
                                ' DEFERRED SALES CHARGE': 'fee2',
                                'COMMISSION': 'fee3',
                                'AMOUNT': 'amount',
                                })

        df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'].dt.year == self.year]
        df = df.sort_values(by='date')
        df['qty'] = np.where(df['type'] == 'SELL', -1 * df['qty'], df['qty'])

        # Get holdings from previous year
        dfprevh = None
        if os.path.isfile(prev_holdings):
            dfprevh = pd.read_json(prev_holdings)
            dfprevh['date'] = pd.to_datetime(dfprevh['date'])
        else:
            print('**** NO PREVIOUS HOLDINGS IS THIS REALLY FIRST YEAR? ****')
        self.dfprevh = dfprevh
        self.df = df

    def trades(self):
        # Create trades dataframe
        if self.df_trades is not None:
            return self.df_trades


        df = self.df[self.df.type.isin(['BUY', 'SELL'])]
        df = pd.concat([self.dfprevh, df])

        self.df_trades = df
        return self.df_trades

    def dividends(self):
        # Create dividends dataframe
        if self.df_dividend is not None:
            return self.df_dividend

        tmp = self.df[self.df.type == 'DIVIDEND_OR_INTEREST'].sort_values(by='transactionDate')
        df = pd.DataFrame()
        df[['symbol', 'date', 'dividend']] = tmp[['transactionItem.instrument.symbol',
                                                  'transactionDate',
                                                  'netAmount']]

        # Filter out transactions for given year
        df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'].dt.year == self.year]

        self.df_dividend = df
        return df

    def tax(self):
        # Create taxs dataframe
        if self.df_tax is not None:
            return self.df_tax

        tmp = self.df[(self.df.type == 'JOURNAL') & (self.df.description == 'W-8 WITHHOLDING')].sort_values(by='transactionDate')
        df = pd.DataFrame()
        df[['symbol', 'date', 'tax']] = tmp[['transactionItem.instrument.symbol',
                                             'transactionDate',
                                             'netAmount']]

        # Filter out transactions for given year
        df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'].dt.year == self.year]

        self.df_tax = df
        return df

class SchwabTransactionsCSV():
    def __init__(self, csv_file, prev_holdings, year) -> None:
        pass

# year=2021
# csv_file = f'data/tdameritrade-{year}.csv'
# prev_holdings = f'data/holdings-{str(year - 1)}.json'   
# td = TDTransactionsCSV(csv_file, prev_holdings, year)  
# df = td.trades()

def read_transactions(format: str, transactions: str, holdings: str, year: int) -> object:
    if format == 'td-json':
        return TDTransactionsJSON(transactions, holdings, year)
    if format == 'td-csv':
        return TDTransactionsCSV(transactions, holdings, year)
    if format == 'schwab-csv':
        return SchwabTransactionsCSV(transactions, holdings, year)
    
