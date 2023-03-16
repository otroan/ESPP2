'''
Morgan Stanley HTML table transaction history normalizer.
'''

# pylint: disable=invalid-name
# pylint: disable=no-name-in-module
# pylint: disable=no-self-argument

import math
from decimal import Decimal
import dateutil.parser as dt
from pandas import read_html
from pydantic import parse_obj_as
from espp2.fmv import FMV
from espp2.datamodels import Transactions, Entry, EntryTypeEnum, Amount
import simplejson as json
import re

currency_converter = FMV()

class ParseState:
    def __init__(self, filename):
        self.source = f'morgan:{filename}'
        self.transactions = []
        self.activity = '<unknown>'
        self.symbol = None
        self.entry_date = None

    def preparse_row(self, row):
        '''Parse common aspects of a row, return True for further parsing'''
        # Set entry-date, or symbol for special header-lines
        date = getitem(row, 'Entry Date')
        if date is None:
            raise ValueError(f'Entry-date is not provided for {row}')

        # Check for indication of which stock is to follow
        m = re.match(r'''^Fund:\s+([A-Za-z]+)\s''', date)
        if m:
            self.symbol = m.group(1)
            if self.symbol == 'Cash':
                self.symbol = None
            return False    # No more parsing needed

        self.entry_date = dt.parse(date)
        self.activity = getitem(row, 'Activity')

        return True

    def deposit(self, qty, purchase_price, description, purchase_date=None):
        assert self.symbol is not None

        r = { 'type': EntryTypeEnum.DEPOSIT,
              'date': self.entry_date,
              'qty': qty,
              'symbol': self.symbol,
              'description': description,
              'purchase_price': purchase_price,
              'purchase_date': purchase_date,
              'source': self.source,
              'broker': 'morgan' }

        self.transactions.append(parse_obj_as(Entry, r))

    def sell(self, qty, price):
        assert self.symbol is not None

        r = { 'type': EntryTypeEnum.SELL,
              'date': self.entry_date,
              'qty': qty,
              'amount': fixup_price(self.entry_date, 'USD', f'{price * -qty}'),
              'symbol': self.symbol,
              'description': self.activity,
              'source': self.source }

        self.transactions.append(parse_obj_as(Entry, r))

    def dividend(self, amount):
        assert self.symbol is not None

        r = { 'type': EntryTypeEnum.DIVIDEND,
              'date': self.entry_date,
              'symbol': self.symbol,
              'amount': amount,
              'source': self.source,
              'description': 'Credit' }

        self.transactions.append(parse_obj_as(Entry, r))

    def dividend_reinvest(self, amount):
        assert self.symbol is not None

        r = { 'type': EntryTypeEnum.DIVIDEND_REINV,
              'date': self.entry_date,
              'symbol': self.symbol,
              'amount': amount,
              'source': self.source,
              'description': 'Debit' }

        self.transactions.append(parse_obj_as(Entry, r))

    def parse_rsu_release(self, row):
        '''Handle what appears to be RSUs added to account'''
        m = re.match(r'''^Release\s+\(([A-Z0-9]+)\)''', self.activity)
        if not m:
            return False

        id = m.group(1)     # Unused for now
        qty, value, ok = getitems(row, 'Number of Shares', 'Book Value')
        if not ok:
            raise ValueError(f'Missing columns for {row}')
        qty = Decimal(qty)
        book_value, currency = morgan_price(value)
        purchase_price = fixup_price2(self.entry_date, currency, book_value / qty)

        self.deposit(qty, purchase_price, 'RS', self.entry_date)
        return True

    def parse_dividend_reinvest(self, row):
        '''Reinvestment of dividend through bying same share'''
        if self.activity != 'You bought (dividend)':
            return False

        qty, price, ok = getitems(row, 'Number of Shares', 'Share Price')
        if not ok:
            raise ValueError(f'Missing columns for {row}')
        qty = Decimal(qty)
        price, currency = morgan_price(price)

        amount = fixup_price(self.entry_date, currency, f'{price * -qty}')
        self.dividend_reinvest(amount)

        purchase_price = fixup_price2(self.entry_date, currency, price)
        self.deposit(qty, purchase_price, 'Dividend re-invest')
        return True

    def parse_sale(self, row):
        if self.activity != 'Sale':
            return False
        qty, price, ok = getitems(row, 'Number of Shares', 'Share Price')
        if not ok:
            raise ValueError(f'Missing colummns for {row}')
        price, currency = morgan_price(price)
        qty = Decimal(qty)
        price = Decimal(price)

        self.sell(qty, price)
        return True

    def parse_deposit(self, row):
        if self.activity != 'Share Deposit' and self.activity != 'Historical Purchase':
            return False
        qty, ok = getitems(row, 'Number of Shares')
        if not ok:
            raise ValueError(f'Missing columns for {row}')
        qty = Decimal(qty)
        price = currency_converter[(self.symbol, self.entry_date)]
        purchase_price = fixup_price2(self.entry_date, 'USD', price)

        self.deposit(qty, purchase_price, 'ESPP', self.entry_date)
        return True

    def parse_dividend_cash(self, row):
        '''This, despite its logged description, results in shares-reinvest'''
        if self.activity != 'Dividend (Cash)':
            return False
        qty, qty_ok = getitems(row, 'Number of Shares')
        cash, cash_ok = getitems(row, 'Cash')

        if qty_ok and cash_ok:
            raise ValueError(f'Unexpected cash+shares for dividend: {row}')

        if qty_ok:
            qty = Decimal(qty)
            price = currency_converter[(self.symbol, self.entry_date)]
            purchase_price = fixup_price2(self.entry_date, 'USD', price)
            self.deposit(qty, purchase_price, 'Dividend re-invest (Cash)', self.entry_date)

        if cash_ok:
            amount = fixup_price(self.entry_date, 'USD', cash)
            self.dividend(amount)

        return True

    def parse_tax_withholding(self, row):
        '''Record taxes withheld'''
        if self.activity != 'Withholding' and self.activity != 'IRS Nonresident Alien Withholding':
            return False
        taxed, ok = getitems(row, 'Cash')
        if not ok:
            raise ValueError(f'Expected Cash data for tax record: {row}')

        amount = fixup_price(self.entry_date, 'USD', taxed)

        r = { 'type': EntryTypeEnum.TAX,
              'date': self.entry_date,
              'amount': amount,
              'symbol': self.symbol,
              'description': self.activity,
              'source': self.source }

        self.transactions.append(parse_obj_as(Entry, r))
        return True

def morgan_price(price_str):
    '''Parse price string.'''
    # import IPython
    # IPython.embed()
    if ' ' in price_str:
        value, currency = price_str.split(' ')
    else:
        value, currency = price_str, 'USD'

    return Decimal(value.replace('$', '').replace(',', '')), currency

def fixup_price(datestr, currency, pricestr, change_sign=False):
    '''Fixup price.'''
    # print('fixup_price:::', datestr, currency, pricestr, change_sign)
    price, currency = morgan_price(pricestr)
    if change_sign:
        price = price * -1
    exchange_rate = currency_converter.get_currency(currency, datestr)
    return {'currency': currency, "value": price, 'nok_exchange_rate': exchange_rate, 'nok_value': price * exchange_rate }


def fixup_price2(date, currency, value):
    '''Fixup price.'''
    exchange_rate = currency_converter.get_currency(currency, date)
    return Amount(currency=currency, value=value,
                   nok_exchange_rate=exchange_rate,
                   nok_value=value * exchange_rate)

def getitem(row, colname):
    '''Get a named item from a row, or None if nothing there'''
    if colname not in row:
        return None
    item = row[colname]
    if isinstance(item, float) and math.isnan(item):
        return None
    assert isinstance(item, str)
    if item == '':
        return None
    return item

def getitems(row, *colnames):
    ok = True
    rc = []
    for cn in colnames:
        i = getitem(row, cn)
        rc.append(i)
        if i is None:
            ok = False
    rc.append(ok)
    return tuple(rc)

def dumpdict(dct):
    print(json.dumps(dct, use_decimal=True, indent=4))

def get_entry_date(row):
    item = getitem(row, 'Entry Date')
    if item is None:
        raise ValueError(f'Expected entry-date for row {row}')
    return dt.parse(item)

def parse_rsu_table(state, recs, filename):
    ignore = {
        'Opening Value': True,
        'Closing Value': True,
    }

    for row in recs:
        if not state.preparse_row(row):
            continue

        if state.parse_rsu_release(row):
            continue

        if state.parse_dividend_reinvest(row):
            continue

        if state.parse_sale(row):
            continue

        if state.parse_dividend_cash(row):
            continue

        if state.parse_tax_withholding(row):
            continue

        if state.activity in ignore:
            continue

        raise ValueError(f'Unknown RSU activity: "{state.activity}"')

def parse_espp_table(state, recs, filename):
    ignore = {
        'Opening Value': True,
        'Closing Value': True,
        'Adhoc Adjustment': True,
        'Transfer out': True,
        'Historical Transaction': True,
        'Wash Sale Adjustment': True,
    }

    for row in recs:
        if not state.preparse_row(row):
            continue

        if state.parse_dividend_reinvest(row):
            continue

        if state.parse_sale(row):
            continue

        if state.parse_deposit(row):
            continue

        if state.parse_dividend_cash(row):
            continue

        if state.parse_tax_withholding(row):
            continue

        if state.activity in ignore:
            continue

        raise ValueError(f'Unknown ESPP activity: "{state.activity}"')

    return state.transactions

def morgan_html_import(html_fd, filename):
    '''Parse Morgan Stanley HTML table file.'''

    state = ParseState(filename)

    # Extract the cash and stocks activity tables
    dfs = read_html(
        html_fd, header=1, attrs={'class': 'sw-datatable', 'id': 'Activity_table'})

    # Expect two tables from this selection; one for RSU and one for the rest (ESPP)
    assert(len(dfs) == 2)

    parse_rsu_table(state, dfs[0].to_dict(orient='records'), filename)
    parse_espp_table(state, dfs[1].to_dict(orient='records'), filename)

    return Transactions(transactions=sorted(state.transactions, key=lambda d: d.date))

def read(html_file, filename='', logger=None) -> Transactions:
    '''Main entry point of plugin. Return normalized Python data structure.'''
    return morgan_html_import(html_file, filename)
