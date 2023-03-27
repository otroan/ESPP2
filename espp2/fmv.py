#!/usr/bin/env python3

'''
The "Fair Market Value" module downloads and stock prices and exchange rates and
caches them in a set of JSON files.
'''

# pylint: disable=invalid-name,line-too-long

import os
import datetime
import json
from enum import Enum
from datetime import date, datetime, timedelta
from typing import Union, Tuple
import logging
from decimal import Decimal
import numpy as np
import urllib3
import logging

logger = logging.getLogger(__name__)

#### ESPP Rate MANUALLY MAINTAINED ####
def get_espp_exchange_rate(ratedate):
    '''Return the 6 month P&L average. Manually maintained for now.'''
    espp = {'2017-06-30':	8.465875,
            '2017-12-29':	8.07695,
            '2018-06-29':	7.96578333,
            '2018-12-31':	8.27031667,
            '2019-06-28':	8.62925833,
            '2019-12-31':	8.92531667,
            '2020-06-30':	9.77359167,
            '2020-12-31':	9.12461667,
            '2021-06-30':	8.4733,
            '2021-12-31':	8.70326667,
            '2022-06-30':	9.07890833,
            '2022-12-30':	10.0731583, }
    return Decimal(espp[ratedate])

class FMVTypeEnum(Enum):
    '''Enum for FMV types'''
    STOCK = 'STOCK'
    CURRENCY = 'CURRENCY'
    DIVIDENDS = 'DIVIDENDS'
    FUNDAMENTALS = 'FUNDAMENTALS'

    def __str__(self):
        return str(self.value)

# Store downloaded files in cache directory under current directory
CACHE_DIR = 'cache'

EODHDKEY='6409ce1fb285f1.01896144'


class FMVException(Exception):
    '''Exception class for FMV module'''

def todate(datestr: str) -> date:
    '''Convert string to datetime'''
    return datetime.strptime(datestr, '%Y-%m-%d').date()

class FMV():
    '''Class implementing the Fair Market Value module. Singleton'''
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FMV, cls).__new__(cls)
            # Put any initialization here.
            if not os.path.exists(CACHE_DIR):
                os.makedirs(CACHE_DIR)

            cls.fetchers = {FMVTypeEnum.STOCK: cls.fetch_stock,
                            FMVTypeEnum.CURRENCY: cls.fetch_currency,
                            FMVTypeEnum.DIVIDENDS: cls.fetch_dividends,
                            FMVTypeEnum.FUNDAMENTALS: cls.fetch_fundamentals,
                            }
            cls.table = {FMVTypeEnum.STOCK: {},
                            FMVTypeEnum.CURRENCY: {},
                            FMVTypeEnum.DIVIDENDS: {},
                            FMVTypeEnum.FUNDAMENTALS: {},
                            }
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
        url = f'https://data.norges-bank.no/api/data/EXR/B.{currency}.NOK.SP?startPeriod=1998&format=csv-:-comma-false-y'
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

    def fetch_dividends(self, symbol):
        '''Returns a dividends object keyed on payment date'''
        http = urllib3.PoolManager()
        # url = f'https://eodhistoricaldata.com/api/div/{symbol}.US?fmt=json&from=2000-01-01&api_token={EODHDKEY}'
        url = f'https://eodhistoricaldata.com/api/div/{symbol}.US?fmt=json&api_token={EODHDKEY}'
        r = http.request('GET', url)
        if r.status != 200:
            raise FMVException(
                f'Fetching dividends data for {symbol} failed {r.status}')
        raw = json.loads(r.data.decode('utf-8'))
        r = {}
        for element in raw:
            r[element['paymentDate']] = element
        return r

    def fetch_fundamentals(self, symbol):
        '''Returns a fundamentals object for symbol'''
        http = urllib3.PoolManager()
        url = f'https://eodhistoricaldata.com/api/fundamentals/{symbol}.US?api_token={EODHDKEY}'
        r = http.request('GET', url)
        if r.status != 200:
            raise FMVException(
                f'Fetching dividends data for {symbol} failed {r.status}')
        raw = json.loads(r.data.decode('utf-8'))
        return raw

    def get_filename(self, fmvtype: FMVTypeEnum, symbol):
        '''Get filename for symbol'''
        return f'{CACHE_DIR}/{fmvtype}_{symbol}.json'

    def load(self, fmvtype: FMVTypeEnum, symbol):
        '''Load data for symbol'''
        filename = self.get_filename(fmvtype, symbol)
        with open(filename, 'r', encoding='utf-8') as f:
            self.table[fmvtype][symbol] = json.load(f)

    def need_refresh(self, fmvtype: FMVTypeEnum, symbol, d: datetime.date):
        '''Check if we need to refresh data for symbol'''
        if symbol not in self.table[fmvtype]:
            return True
        fetched = self.table[fmvtype][symbol]['fetched']
        fetched = datetime.strptime(fetched, '%Y-%m-%d').date()
        if d and d > fetched:
            return True
        return False

    def refresh(self, symbol: str, d: datetime.date, fmvtype: FMVTypeEnum):
        '''Refresh data for symbol if needed'''
        if not self.need_refresh(fmvtype, symbol, d):
            return

        filename = self.get_filename(fmvtype, symbol)

        # Try loading from cache
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                self.table[fmvtype][symbol] = json.load(f)
                if not self.need_refresh(fmvtype, symbol, d):
                    return
        except IOError:
            pass

        data = self.fetchers[fmvtype](self, symbol)

        logging.info('Caching data for %s to %s', symbol, filename)
        data['fetched'] = str(date.today())
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        self.table[fmvtype][symbol] = data

    def extract_date(self, input_date: Union[str, datetime, datetime.date]) -> Tuple[datetime.date, str]:
        '''Extract date component from input string or datetime object'''
        if isinstance(input_date, str):
            try:
                date_obj = datetime.strptime(input_date, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError(f"Invalid date format '{input_date}'. Use 'YYYY-MM-DD' format.")
        elif isinstance(input_date, datetime):
            date_obj = input_date.date()
        elif isinstance(input_date, date):
            date_obj = input_date
        else:
            raise TypeError(f"Input must be string or datetime object, not {type(input_date)}")
        date_str = date_obj.isoformat()
        return date_obj, date_str

    def __getitem__(self, item):
        symbol, itemdate = item
        fmvtype = FMVTypeEnum.STOCK
        itemdate, date_str = self.extract_date(itemdate)
        self.refresh(symbol, itemdate, fmvtype)
        for _ in range(5):
            try:
                return Decimal(str(self.table[fmvtype][symbol][date_str]))
            except KeyError:
                # Might be a holiday, iterate backwards
                itemdate -= timedelta(days=1)
                date_str = str(itemdate)
        return np.nan

    def get_currency(self, currency: str, date_union: Union[str, datetime]) -> float:
        '''Get currency value. If not found, iterate backwards until found.'''
        itemdate, date_str = self.extract_date(date_union)

        if currency == 'ESPPUSD':
            try:
                return get_espp_exchange_rate(date_str)
            except KeyError:
                # Missing ESPP data for this date
                logger.error("Missing ESPP data for %s", date_str)
                # Fall-back to USD
                currency = 'USD'
        self.refresh(currency, itemdate, FMVTypeEnum.CURRENCY)

        for _ in range(6):
            try:
                return Decimal(str(self.table[FMVTypeEnum.CURRENCY][currency][date_str]))
            except KeyError:
                # Might be a holiday, iterate backwards
                itemdate -= timedelta(days=1)
                date_str = str(itemdate)
        raise FMVException(f'No currency data for {currency} on {date_str}')

    def get_dividend(self, dividend: str, payment_date: Union[str, datetime]) -> Tuple[date, date, Decimal]:
        '''Lookup a dividends record given the paydate.'''
        itemdate, date_str = self.extract_date(payment_date)
        self.refresh(dividend, itemdate, FMVTypeEnum.DIVIDENDS)
        for _ in range(5):
            try:
                divinfo = self.table[FMVTypeEnum.DIVIDENDS][dividend][date_str]
                exdate = todate(divinfo['date'])
                declarationdate = todate(
                    divinfo['declarationDate']) if divinfo['declarationDate'] else exdate
                return exdate, declarationdate, Decimal(str(divinfo['value']))
            except KeyError:
                # Might be a holiday, iterate backwards
                itemdate -= timedelta(days=1)
                date_str = str(itemdate)
        raise FMVException(f'No dividends data for {dividend} on {date_str}')

    def get_fundamentals(self, symbol: str) -> dict:
        '''Lookup a symbol and return fundamentals'''
        self.refresh(symbol, None, FMVTypeEnum.FUNDAMENTALS)

        try:
            return self.table[FMVTypeEnum.FUNDAMENTALS][symbol]
        except KeyError as e:
            raise FMVException(f'No fundamentals data for {symbol}') from e

if __name__ == '__main__':

    fmv = FMV()
    print('LOOKING UP DATA', fmv[FMVTypeEnum.STOCK, 'CSCO', '2021-12-31'])
    # print('LOOKING UP DATA', f['CSCO', '2022-12-31'])
    print('LOOKING UP DATA', fmv[FMVTypeEnum.STOCK, 'SLT', '2021-12-31'])
    # f.fetch_currency('USD')
    print('LOOKING UP DATA USD2NOK', fmv.get_currency('USD', '2021-12-31'))

    print('LOOKING UP DIVIDENDS', fmv.get_dividend('CSCO', '2023-01-25'))

    print('CISCO FUNDAMETNALS', fmv.get_fundamentals('CSCO'))
    fundamentals = fmv.get_fundamentals('CSCO')
    print('CISCO FUNDAMETNALS', fundamentals['ISIN'])
