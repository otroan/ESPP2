#!/usr/bin/env python3

from ast import AugAssign
import datetime
from typing import IO
import urllib3
from urllib3 import request
import certifi
import json
from datetime import date, datetime, timedelta
from typing import Union, Tuple
import numpy as np

class FMV():
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            print('Creating the object')
            cls._instance = super(FMV, cls).__new__(cls)
            # Put any initialization here.
            cls.symbols = {}
        return cls._instance
    
    def fetch_stock(self, symbol):
        '''Returns a dictionary of date and closing value'''
        apikey='LN6PYRQ0I5LKDY51'
        http = urllib3.PoolManager()
        # The REST api is described here: https://www.alphavantage.co/documentation/
        url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&outputsize=full&' \
                'apikey={apikey}'
        r = http.request('GET', url)
        if r.status != 200:
            raise Exception(f'Fetching stock data for {symbol} failed {r.status}')
        raw = json.loads(r.data.decode('utf-8'))
        return {k: float(v['4. close'])
               for k, v in raw['Time Series (Daily)'].items()}

    def fetch_currency(self, currency):
        '''Returns a dictionary of date and closing value'''
        http = urllib3.PoolManager()
        # The REST api is described here: https://app.norges-bank.no/query/index.html#/no/
        # url = f'https://data.norges-bank.no/api/data/EXR/B.{currency}.NOK.SP?startPeriod=2000&format=sdmx-json'
        url = f'https://data.norges-bank.no/api/data/EXR/B.{currency}.NOK.SP?startPeriod=2000&format=csv-:-comma-false-y'
        r = http.request('GET', url)
        if r.status != 200:
            raise Exception(f'Fetching currency data for {currency} failed {r.status}')
        cur = {}
        for i, line in enumerate(r.data.decode('utf-8').split('\n')):
            if i == 0 or ',' not in line: continue  # Skip header and blank lines
            d, exr = line.strip().split(',')
            c = float(exr.strip('"'))
            d = d.strip('"')
            cur[d] = c
        return cur

    def get_filename(self, symbol):
        return f'data/{symbol}.json'

    def load(self, symbol):
        filename = self.get_filename(symbol)
        with open(filename, 'r') as f:
            self.symbols[symbol] = json.load(f)

    def need_refresh(self, symbol, d: datetime.date):
        if symbol not in self.symbols:
            return True
        fetched = self.symbols[symbol]['fetched']
        fetched = datetime.strptime(fetched, '%Y-%m-%d').date()
        if d > fetched:
            return True
        return False

    def refresh(self, symbol, d: datetime.date, currency):
        if not self.need_refresh(symbol, d):
            return

        filename = self.get_filename(symbol)

        # Try loading from cache
        try:
            with open(filename, 'r') as f:
                self.symbols[symbol] = json.load(f)
                if not self.need_refresh(symbol, d):
                    return
        except IOError:
            pass

        if currency:
            data = self.fetch_currency(symbol)
            print('DATA', data)
        else:
            data = self.fetch_stock(symbol)

        print(f'Writing to {filename}')
        data['fetched'] = str(date.today())
        with open(filename, 'w') as f:
            json.dump(data, f)

        self.symbols[symbol] = data

    def parse_date(self, date: Union[str, datetime]) -> Tuple[datetime.date, str]:
        '''Parse date/timestamp'''
        if type(date) is str:
            date = datetime.strptime(date, '%Y-%m-%d').date()
        else:
            date = date.date()
        date_str = str(date)
        return date, date_str


    def __getitem__(self, item):
        symbol, date = item
        date, date_str = self.parse_date(date)
        self.refresh(symbol, date, False)
        for i in range(5):
            try:
                return self.symbols[symbol][date_str]
            except KeyError:
                # Might be a holiday, iterate backwards
                date -= timedelta(days=1)
                date_str = str(date)
        return np.nan

    def get_currency(self, currency:str, date: Union[str, datetime]) -> float:
        date, date_str = self.parse_date(date)
        self.refresh(currency, date, True)
        for i in range(5):
            try:
                return self.symbols[currency][date_str]
            except KeyError:
                # Might be a holiday, iterate backwards
                date -= timedelta(days=1)
                date_str = str(date)
        return np.nan


if __name__ == '__main__':

    f = FMV()
    print('LOOKING UP DATA', f['CSCO', '2021-12-31'])

    #print('LOOKING UP DATA', f['CSCO', '2022-12-31'])

    print('LOOKING UP DATA', f['SLT', '2021-12-31'])

    #f.fetch_currency('USD')
    print('LOOKING UP DATA USD2NOK', f.get_currency('USD', '2021-12-31'))
