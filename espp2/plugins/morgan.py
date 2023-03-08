'''
Morgan Stanley HTML table transaction history normalizer.
'''

# pylint: disable=invalid-name

from decimal import Decimal
import dateutil.parser as dt
from pandas import read_html
from pydantic import parse_obj_as
from espp2.fmv import FMV
from espp2.datamodels import Transactions, Entry, EntryTypeEnum, Amount
import math

currency_converter = FMV()
def morgan_price(price_str):
    '''Parse price string.'''
    # import IPython
    # IPython.embed()
    value, currency = price_str.split(' ')
    return Decimal(value.replace('$', '').replace(',', '')), currency

def fixup_price(datestr, currency, pricestr, change_sign=False):
    '''Fixup price.'''
    print('fixup_price:::', datestr, currency, pricestr, change_sign)
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

def table(recs):
    trans = []
    for e in recs:
        # print('RECORD:', e)
        # Header row
        if e['Activity'] == e['Entry Date']:
            if e['Entry Date'].startswith('Fund: Cash'):
                cash = True
            elif e['Entry Date'].startswith('Fund: CSCO'):
                # TODO: Handle other symbols
                cash = False
                symbol = 'CSCO'
            continue
        if e['Activity'] in ('Historical Transaction', 'Closing Value'):
            continue

        d = dt.parse(e['Entry Date'])

        if cash:
            # TODO: Handle cash
            continue

        r : dict
        if e['Activity'] == 'Opening Balance' or e['Activity'].startswith('Release'):
            # Seems like a BUY entry
            t = EntryTypeEnum.DEPOSIT
            qty = Decimal(e['Number of Shares'])
            book_value, currency = morgan_price(e['Book Value'])
            purchase_price = fixup_price2(d, currency, book_value / qty)
            
            r = {'type': t, 'date': d, 'qty': qty, 'symbol': symbol,
                 'description': e['Activity'],
                 'purchase_price': purchase_price, }

        elif e['Activity'] in ('Withholding', 'IRS Nonresident Alien Withholding'):
            t = EntryTypeEnum.TAX
            amount = fixup_price(d, "USD", e['Cash'])
            r = {'type': t, 'date': d, 'amount': amount, 'symbol': symbol, 'description': e['Activity']}

        elif e['Activity'] == 'Dividend (Cash)':
            t = EntryTypeEnum.DIVIDEND
            amount = fixup_price(d, "USD", e['Cash'])

            r = {'type': t, 'date': d, 'amount': amount, 'symbol': symbol}

        elif e['Activity'] == 'You bought (dividend)':
            # {'Entry Date': '30-Jan-2023', 'Activity': 'You bought (dividend)',
            #  'Type of Money': 'Employee', 'Cash': '$-7.43 USD', 'Number of Shares': '0.154000',
            #  'Share Price': '$48.31 USD', 'Book Value': '$7.43 USD', 'Market Value': nan}
            t = EntryTypeEnum.DIVIDEND_REINV
            qty = Decimal(e['Number of Shares'])
            # book_value, currency = morgan_price(e['Book Value'])
            # purchase_price = fixup_price(d, "USD", e['Share Price'])
            amount = fixup_price(d, "USD", e['Cash'])

            r = {'type': t, 'date': d, 'qty': qty, 'symbol': symbol,
                 'description': e['Activity'],
                 'amount': amount, }


        elif e['Activity'] == 'Sale':
            # {'Entry Date': '06-Jan-2023', 'Activity': 'Sale', 'Type of Money': 'Employee',
            #  'Cash': nan, 'Number of Shares': '-23.000000', 'Share Price': '$47.86 USD',
            #  'Book Value': '$-1,009.93 USD', 'Market Value': nan}

            t = EntryTypeEnum.SELL
            qty = Decimal(e['Number of Shares'])
            if not math.isnan(e['Cash']):
                amount = fixup_price(d, "USD", e['Cash'])
            else:
                amount = fixup_price(d, "USD", e['Book Value'])

            r = {'type': t, 'date': d, 'qty': qty, 'amount': amount, 'symbol': symbol, 'description': e['Activity']}

        elif e['Activity'] == 'Cash Transfer Out':
            # TODO
            t = EntryTypeEnum.WIRE
            continue

        elif e['Activity'] == 'Opening Value':
            # Opening Value of cash in shares account
            continue

        else:
            raise Exception('Unknown activity type: {}'.format(e['Activity']))
        print('R', r)

        r['source'] = 'morgan'
        trans.append(parse_obj_as(Entry, r))
    return trans

def morgan_html_import(html_fd):
    '''Parse Morgan Stanley HTML table file.'''


    # Extract the cash and stocks activity tables
    dfs = read_html(
        html_fd, header=1, attrs={'class': 'sw-datatable', 'id': 'Activity_table'})

    trans = []
    for df in dfs:
        trans += table(df.to_dict(orient='records'))

    return Transactions(transactions=trans)

def read(html_file, logger) -> Transactions:
    '''Main entry point of plugin. Return normalized Python data structure.'''
    return morgan_html_import(html_file)
