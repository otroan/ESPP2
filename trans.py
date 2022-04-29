#!/usr/bin/env python3

import sys
from telnetlib import IP
import pandas as pd
import numpy as np
import json
import os
from fmv import FMV
import logging
from schwab import SchwabCSVImport

class TDTransactionsJSON():
    def __init__(self, json_file, prev_holdings, year) -> None:
        with open(json_file, 'r') as jf:
                json_data = json.load(jf)
        tmp = pd.json_normalize(json_data)
        self.df_trades = None
        self.df_dividend = None
        self.df_tax = None
        self.df_cash = None
        self.year = year

        df = pd.DataFrame(columns=['type', 'symbol', 'date', 'amount', 'price'])
        for i, r in tmp.iterrows():
            if ('transactionItem.instrument.assetType' in r) and r['transactionItem.instrument.assetType'] == 'EQUITY':
                if r.type == 'TRADE' or r.type == 'RECEIVE_AND_DELIVER':
                    t = r['transactionItem.instruction']
                elif r.type == 'DIVIDEND_OR_INTEREST':
                    t = 'DIVIDEND'
            elif r.type == 'JOURNAL' and r.description == 'W-8 WITHHOLDING':
                t = 'DIVIDEND-TAX'
            elif r.type == 'ELECTRONIC_FUND':
                t = 'WIRE'
            elif r.type == 'DIVIDEND_OR_INTEREST':
                t = 'INTEREST'
            elif r.type == 'RECEIVE_AND_DELIVER':
                t = 'CASH'
            else:
                raise Exception(f'UNKNOWN TRANSACTION {r}')
                t = f'UKNOWN {r.type}'
                
            df.loc[len(df.index)] = t, r['transactionItem.instrument.symbol'], r['transactionDate'], r['transactionItem.amount'], r['transactionItem.price']
        print('TRANSACTIONS\n', df)        
        df[['type', 'symbol', 'assettype', 'date',
            'qty', 'price', 'cost', 'amount']] = tmp[['transactionItem.instruction',
                                                      'transactionItem.instrument.symbol',
                                                      'transactionItem.instrument.assetType',
                                                      'transactionDate',
                                                      'transactionItem.amount',
                                                      'transactionItem.price',
                                                      'transactionItem.cost',
                                                      'netAmount']]
        df['qty'] = np.where(df['type'] == 'SELL', -1 * df['qty'], df['qty'])

        # Filter out transactions for given year
        df['date'] = pd.to_datetime(df['date'])
        df = df[df['date'].dt.year == self.year]
        df = df.sort_values(by='date')
        #df['price_nok'] = df.apply(lambda row: (row['price'] * f.get_currency('USD', row['date'])), axis=1)
        df['tax_deduction'] = 0

        # Get holdings from previous year
        dfprevh = None
        if prev_holdings and os.path.isfile(prev_holdings):
            dfprevh = pd.read_json(prev_holdings)
            dfprevh['date'] = pd.to_datetime(dfprevh['date'])
        else:
            print('*** NO PREVIOUS HOLDINGS IS THIS REALLY FIRST YEAR? ***', file=sys.stderr)
        self.dfprevh = dfprevh

        if self.dfprevh is not None:
            df = pd.concat([self.dfprevh, df], ignore_index=True)

        df['idx'] = pd.Index(range(len(df.index)))
        
        self.df = df
        
        print('TRANSACTIONS\n', df)

    def trades(self):
        return pd.DataFrame
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
            'qty', 'price', 'cost', 'assettype', 'amount']] = tmp[['transactionItem.instruction',
                                                                   'transactionItem.instrument.symbol',
                                                                   'transactionDate',
                                                                   'transactionItem.amount',
                                                                   'transactionItem.price',
                                                                   'transactionItem.cost',
                                                                   'transactionItem.instrument.assetType'
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
            df = pd.concat([self.dfprevh, df], ignore_index=True)

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



class TDTransactionsCSV():
    @staticmethod
    def description_to_type(value):
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
        if value.startswith('FREE BALANCE INTEREST'):
            return 'INTEREST'
        if value.startswith('REBATE'):
            return 'REBATE'
        if value.startswith('WIRE INCOMING'):
            return 'DEPOSIT'
        if value.startswith('OFF-CYCLE INTEREST'):
            return 'INTEREST'
        raise Exception(f'Unknown transaction entry {value}')
        return value

    def __init__(self, csv_file, prev_holdings, year) -> None:
        logging.info(f'Reading transactions from {csv_file}')
        df = pd.read_csv(csv_file, converters={'DESCRIPTION': self.description_to_type})
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
        print('READ:', df)
        
        ### TODO: Merge Fee columns. Drop other columns
        df['fees'] = df[['fee1', 'fee2', 'fee3']].sum(axis=1)
        
        df['date'] = pd.to_datetime(df['date'], utc=True)
        l = len(df)
        df = df[df['date'].dt.year == self.year]
        if l != len(df):
            logging.warning(f'Filtered out transaction entries from another year. {l} {len(df)}')
            
        df['qty'] = np.where(df['type'] == 'SELL', -1 * df['qty'], df['qty'])
        df['tax_deduction'] = 0

        # Get holdings from previous year
        self.dfprevh = None
        if prev_holdings and os.path.isfile(prev_holdings):
            logging.info(f'Reading previous holdings from {prev_holdings}')
            with open (prev_holdings) as f:
                data = json.load(f)
            #dfprevh = pd.from_dict(data['shares'])
            dfprevh = pd.DataFrame(data['stocks'])
            dfprevh['type'] = 'BUY'
            dfprevh['date'] = pd.to_datetime(dfprevh['date'], utc=True)
            self.dfprevh = dfprevh
            df = pd.concat([dfprevh, df], ignore_index=True)

            dfprevh_cash = pd.DataFrame(data['cash'])

            if not dfprevh_cash.empty:
                dfprevh_cash['date'] = pd.to_datetime(dfprevh_cash['date'], utc=True)
            self.dfprevh_cash = dfprevh_cash
        else:
            logging.error('No previous year holdings, is this really the first year?')

        df = df.sort_values(by='date')
        df['idx'] = pd.Index(range(len(df.index)))
        self.df = df
        
        self.df_trades = self.df[self.df.type.isin(['BUY', 'SELL'])]
        self.df_dividend = self.df[self.df.type == 'DIVIDEND']
        self.df_tax = self.df[self.df.type == 'TAX']
        self.df_cash = self.df[self.df.type == 'WIRE']
        self.df_fees = self.df[self.df.type == 'FEE'] ### TODO: FIX FIX

    def fees(self):
        return self.df_fees

    def trades(self):
        return self.df_trades

    def dividends(self):
        return self.df_dividend

    def tax(self):
        return self.df_tax

    def cash(self):
        return self.df_cash

class SchwabTransactionsCSV():
    @staticmethod
    def description_to_type(value):
        c = {'Wire Transfer': 'WIRE',
             'Service Fee': 'FEE',
             'Deposit': 'DEPOSIT', ## DEPOSIT EQUITY / DEPOSIT CASH
             'Dividend': 'DIVIDEND',
             'Tax Withholding': 'TAX',
             'Dividend Reinvested': 'DIV_REINVEST',
             'Sale': 'SELL',
             }
        if value in c:
            return c[value]
        raise Exception(f'Unknown transaction entry {value}')

    def __init__(self, csv_file, prev_holdings, year) -> None:
        self.df_trades = None
        self.df_dividend = None
        self.df_tax = None
        self.year = year

        csv = SchwabCSVImport(logging, csv_file)
        df = pd.json_normalize(csv)
        
        df = df.rename(columns={'DATE': 'date',
                        'ACTION': 'type',
                        'SYMBOL': 'symbol',
                        'QUANTITY': 'qty',
                        'PRICE': 'price',
                        'FEES & COMMISSIONS': 'fee',
                        'AMOUNT': 'amount',
                        })

        df['date'] = pd.to_datetime(df['date'], utc=True)
        l = len(df)
        df = df[df['date'].dt.year == self.year]
        if l != len(df):
            logging.warning(f'Filtered out transaction entries from another year. {l} {len(df)}')

        df['type'] = df.apply(lambda x: self.description_to_type(x.type), axis=1)
        df['amount'] = df['amount'].replace('\$|,', '', regex=True)
        df['amount'] = pd.to_numeric(df['amount'])
        df['fee'] = df['fee'].replace('\$|,', '', regex=True)
        df['fee'] = pd.to_numeric(df['fee'])
        df['qty'] = pd.to_numeric(df['qty'])
        df['price'] = 0
        for i, r in df.iterrows():
            if r.type == 'SELL':
                df.loc[i, 'price'] = r.amount / r.qty
            if r.type == 'DEPOSIT' and r.DESCRIPTION == 'RS':
                assert(len(r.subdata) == 1)
                df.loc[i, 'price'] = r.subdata[0]['VEST FMV']
            if r.type == 'DEPOSIT' and r.DESCRIPTION == 'ESPP':
                df.loc[i, 'price'] = r.subdata[0]['PURCHASE FMV']
            if r.type == 'DEPOSIT' and r.DESCRIPTION == 'Div Reinv':
                df.loc[i, 'price'] = r.subdata[0]['PURCHASE PRICE']
                
        df['price'] = df['price'].replace('\$|,', '', regex=True)
        df['price'] = pd.to_numeric(df['price'])

        df['tax_deduction'] = 0
        df['qty'] = np.where(df['type'] == 'SELL', -1 * df['qty'], df['qty'])
        

        # Get holdings from previous year
        self.dfprevh = None
        if prev_holdings and os.path.isfile(prev_holdings):
            logging.info(f'Reading previous holdings from {prev_holdings}')
            with open (prev_holdings) as f:
                data = json.load(f)
            #dfprevh = pd.from_dict(data['shares'])
            dfprevh = pd.DataFrame(data['stocks'])
            dfprevh['type'] = 'BUY'
            dfprevh['date'] = pd.to_datetime(dfprevh['date'], utc=True)
            self.dfprevh = dfprevh
            df = pd.concat([dfprevh, df], ignore_index=True)

            if len(data['cash']) != 0:
                dfprevh_cash = pd.DataFrame(data['cash'])
                dfprevh_cash['date'] = pd.to_datetime(dfprevh_cash['date'], utc=True)
                self.dfprevh_cash = dfprevh_cash
            else:
                self.dfprevh_cash = pd.DataFrame
        else:
            logging.error('No previous year holdings, is this really the first year?')

        df = df.sort_values(by='date')
        df['idx'] = pd.Index(range(len(df.index)))
        self.df = df
        
        self.df_trades = self.df[(self.df.type.isin(['BUY', 'SELL']) | ((self.df.type == 'DEPOSIT') & (self.df.symbol != "")))]
        self.df_dividend = self.df[self.df.type == 'DIVIDEND']
        self.df_tax = self.df[self.df.type == 'TAX']
        self.df_cash = self.df[self.df.type == 'WIRE']
        self.df_fees = self.df[self.df.type == 'FEE']

    def trades(self):
        return self.df_trades

    def dividends(self):
        return self.df_dividend

    def tax(self):
        return self.df_tax

    def cash(self):
        return self.df_cash

    def fees(self):
        return self.df_fees

        
        


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
    
