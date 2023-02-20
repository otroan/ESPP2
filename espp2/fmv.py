#!/usr/bin/env python3

'''
The "Fair Market Value" module downloads and stock prices and exchange rates and
caches them in a set of JSON files.
'''

# pylint: disable=invalid-name,line-too-long

import os
import datetime
import json
from datetime import date, datetime, timedelta
from typing import Union, Tuple
import logging
from decimal import Decimal
import numpy as np
import urllib3

# Store downloaded files in cache directory under current directory
CACHE_DIR = 'cache'


class FMVException(Exception):
    '''Exception class for FMV module'''


class FMV():
    '''Class implementing the Fair Market Value module. Singleton'''
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FMV, cls).__new__(cls)
            # Put any initialization here.
            cls.symbols = {}
            if not os.path.exists(CACHE_DIR):
                os.makedirs(CACHE_DIR)
        return cls._instance

    def fetch_stock(self, symbol):
        '''Returns a dictionary of date and closing value'''
        # apikey = 'LN6PYRQ0I5LKDY51'
        http = urllib3.PoolManager()
        # The REST api is described here: https://www.alphavantage.co/documentation/
        url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&outputsize=full&' \
            'apikey={apikey}'
        r = http.request('GET', url)
        if r.status != 200:
            raise FMVException(
                f'Fetching stock data for {symbol} failed {r.status}')
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
            raise FMVException(
                f'Fetching currency data for {currency} failed {r.status}')
        cur = {}
        for i, line in enumerate(r.data.decode('utf-8').split('\n')):
            if i == 0 or ',' not in line:
                continue  # Skip header and blank lines
            d, exr = line.strip().split(',')
            c = float(exr.strip('"'))
            d = d.strip('"')
            cur[d] = c
        return cur

    def get_filename(self, symbol):
        '''Get filename for symbol'''
        return f'{CACHE_DIR}/{symbol}.json'

    def load(self, symbol):
        '''Load data for symbol'''
        filename = self.get_filename(symbol)
        with open(filename, 'r', encoding='utf-8') as f:
            self.symbols[symbol] = json.load(f)

    def need_refresh(self, symbol, d: datetime.date):
        '''Check if we need to refresh data for symbol'''
        if symbol not in self.symbols:
            return True
        fetched = self.symbols[symbol]['fetched']
        fetched = datetime.strptime(fetched, '%Y-%m-%d').date()
        if d > fetched:
            return True
        return False

    def refresh(self, symbol, d: datetime.date, currency):
        '''Refresh data for symbol if needed'''
        if not self.need_refresh(symbol, d):
            return

        filename = self.get_filename(symbol)

        # Try loading from cache
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                self.symbols[symbol] = json.load(f)
                if not self.need_refresh(symbol, d):
                    return
        except IOError:
            pass

        if currency:
            data = self.fetch_currency(symbol)
        else:
            data = self.fetch_stock(symbol)

        logging.info('Caching data for %s to %s', symbol, filename)
        data['fetched'] = str(date.today())
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        self.symbols[symbol] = data

    def parse_date(self, itemdate: Union[str, datetime]) -> Tuple[datetime.date, str]:
        '''Parse date/timestamp'''
        if isinstance(itemdate, str):
            itemdate = datetime.strptime(itemdate, '%Y-%m-%d').date()
        else:
            itemdate = itemdate.date()
        date_str = str(itemdate)
        return itemdate, date_str

    def __getitem__(self, item):
        symbol, itemdate = item
        itemdate, date_str = self.parse_date(itemdate)
        self.refresh(symbol, itemdate, False)
        for _ in range(5):
            try:
                return Decimal(str(self.symbols[symbol][date_str]))
            except KeyError:
                # Might be a holiday, iterate backwards
                itemdate -= timedelta(days=1)
                date_str = str(itemdate)
        return np.nan

    def get_currency(self, currency: str, date_union: Union[str, datetime]) -> float:
        '''Get currency value. If not found, iterate backwards until found.'''
        itemdate, date_str = self.parse_date(date_union)
        self.refresh(currency, itemdate, True)
        for _ in range(6):
            try:
                return Decimal(str(self.symbols[currency][date_str]))
            except KeyError:
                # Might be a holiday, iterate backwards
                itemdate -= timedelta(days=1)
                date_str = str(itemdate)
        raise FMVException(f'No currency data for {currency} on {date_str}')


if __name__ == '__main__':

    fmv = FMV()
    print('LOOKING UP DATA', fmv['CSCO', '2021-12-31'])
    # print('LOOKING UP DATA', f['CSCO', '2022-12-31'])
    print('LOOKING UP DATA', fmv['SLT', '2021-12-31'])
    # f.fetch_currency('USD')
    print('LOOKING UP DATA USD2NOK', fmv.get_currency('USD', '2021-12-31'))
