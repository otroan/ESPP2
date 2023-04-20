'''
Schwab CSV normalizer.
'''

# pylint: disable=invalid-name, too-many-locals, too-many-branches

import csv
from decimal import Decimal
import codecs
import io
import logging
import dateutil.parser as dt
from espp2.fmv import FMV
from espp2.datamodels import Transactions, Amount

logger = logging.getLogger(__name__)

def schwab_csv_import(fd):
    '''Parse Schwab CSV file.'''

    data = []

    # Fastapi passes in binary file and CLI passes in a TextIOWrapper
    if isinstance(fd, io.TextIOWrapper):
        reader = csv.reader(fd)
    else:
        reader = csv.reader(codecs.iterdecode(fd,'utf-8'))

    try:
        next(reader)
        header = next(reader)
        assert header == ['Date', 'Action', 'Symbol', 'Description',
                          'Quantity', 'Fees & Commissions', 'Disbursement Election', 'Amount']

        def field(x):
            return header.index(x)
        data = []
        while True:
            row = next(reader)
            if len(row) == 1:
                continue
            subheader = None

            while row[field('Date')] == '':
                if not subheader:
                    subheader = row
                    row = next(reader)
                if 'subdata' not in data[-1]:
                    data[-1]['subdata'] = []
                data[-1]['subdata'].append({subheader[v].upper():
                                            k for v, k in enumerate(row) if v != 0})
                row = next(reader)
                subheader = None
            data.append({header[v].upper(): k for v, k in enumerate(row)})
    except StopIteration:
        pass
    return data

def action_to_type(value, description):
    '''Normalize transaction type.'''
    action = {'Wire Transfer': 'WIRE',
         'Service Fee': 'FEE',
         'Deposit': 'DEPOSIT',  # DEPOSIT EQUITY / DEPOSIT CASH
         'Dividend': 'DIVIDEND',
         'Tax Withholding': 'TAX',
         'Tax Reversal': 'TAXSUB',
         'Dividend Reinvested': 'DIVIDEND_REINV',
         'Sale': 'SELL',
         'Quick Sale': 'SELL',
         'Journal': 'WIRE',
         'Adjustment': 'CASHADJUST',
         }
    # if value == 'Deposit' and description == 'Div Reinv':
    #     return 'BUY'
    if value in action:
        return action[value]
    raise ValueError(f'Unknown transaction entry: {value} {description}')


def fixup_date(datestr):
    '''Fixup date'''
    d =  dt.parse(datestr)
    return d.strftime('%Y-%m-%d')

currency_converter = FMV()
def fixup_price(datestr, currency, pricestr, change_sign=False):
    '''Fixup price.'''
    price = Decimal(pricestr.replace('$', '').replace(',', ''))
    if change_sign:
        price = price * -1
    exchange_rate = currency_converter.get_currency(currency, datestr)
    return {'currency': currency, "value": price,
            'nok_exchange_rate': exchange_rate,
            'nok_value': price * exchange_rate}

def fixup_number(numberstr):
    '''Convert string to number.'''
    try:
        return Decimal(numberstr)
    except ValueError:
        return ""

def subdata(action, description, date, value):
    '''Parse Schwab sub-data field.'''

    datefields = ['purchase_date',
                  'subscription_date', 'award_date', 'vest_date']
    numberfields = ['shares']
    pricefields = ['purchase_price', 'purchase_fmv',
                   'subscription_fmv', 'vest_fmv', 'sale_price', 'gross_proceeds']
    key_conv = {'PURCHASE DATE': 'purchase_date',
                'PURCHASE PRICE': 'purchase_price',
                'PURCHASE FMV': 'purchase_fmv',       # For ESPP this is our cost basis
                'SUBSCRIPTION FMV': 'subscription_fmv',
                'SUBSCRIPTION DATE': 'subscription_date',
                'AWARD DATE': 'award_date',
                'AWARD ID': 'award_id',
                'VEST DATE': 'vest_date',
                'VEST FMV': 'purchase_price',
                'TYPE': 'subtype',
                'SHARES': 'shares',
                'SALE PRICE': 'sale_price',
                'GROSS PROCEEDS': 'gross_proceeds',
                'DISPOSITION TYPE': 'disposition_type',
                'GRANT ID': 'grant_id',
                }

    if not isinstance(value, list):
        return value
    newlist = []
    for sub in value:
        newv = {}
        is_espp = bool(action == 'DEPOSIT' and description == 'ESPP')
        for k, subdata_item in sub.items():
            if not subdata_item:
                continue
            newkey = key_conv.get(k, k)

            if newkey in datefields:
                newv[newkey] = fixup_date(subdata_item)
            # elif newkey in pricefields:
            #     newv[newkey] = fixup_price(subdata_item)
            elif newkey in numberfields:
                newv[newkey] = fixup_number(subdata_item)
            elif newkey in pricefields:
                newv[newkey] = fixup_price(date, 'USD', subdata_item)
            else:
                newv[newkey] = subdata_item
        if is_espp:
            # purchase_price is the plan price, not our cost basis
            newv['plan_purchase_price'] = newv.pop('purchase_price')
            purchase_price = newv.pop('purchase_fmv')['value']
            purchase_date = newv['purchase_date']
            newv['purchase_price'] = Amount(
                amountdate=purchase_date, value=purchase_price, currency='ESPPUSD')
            newv['date'] = purchase_date

        newv['broker'] = 'schwab'
        # for price in pricefields:
        #     if price in newv:
        #         newv[price] = fixup_price(date, 'USD', newv[price])

        newlist.append(newv)
    return newlist

def read(csv_file, filename='') -> Transactions:
    '''Main entry point of plugin. Return normalized Python data structure.'''

    key_conv = {'DATE': 'date',
                'ACTION': 'type',
                'SYMBOL': 'symbol',
                'QUANTITY': 'qty',
                'PRICE': 'price',
                'FEES & COMMISSIONS': 'fee',
                'AMOUNT': 'amount',
                'DESCRIPTION': 'description',
                }
    pricefields = ['amount', 'fee']
    numberfields = ['qty']

    csv_data = schwab_csv_import(csv_file)
    newlist = []
    for csv_item in csv_data:
        newv = {}
        action = action_to_type(csv_item['ACTION'], csv_item['DESCRIPTION'])
        description = csv_item['DESCRIPTION']
        data_item = None
        for k,data_item in csv_item.items():
            newkey = key_conv.get(k, k)
            if not data_item:
                continue
            if newkey == 'date':
                newv[newkey] = fixup_date(data_item)
            # elif newkey in pricefields:
            #     newv[newkey] = fixup_price(data_item)
            elif newkey in numberfields:
                newv[newkey] = fixup_number(data_item)
            elif newkey == 'type':
                newv[newkey] = action_to_type(data_item, description)
            else:
                newv[newkey] = data_item
        if 'subdata' in newv:
            data_item = '' if not data_item else data_item
            if len(newv['subdata']) == 1:
                newv |= subdata(action, description, newv['date'], data_item)[0]
                newv.pop('subdata')
            else:
                newv[newkey] = subdata(action, description, newv['date'], data_item)

        for price in pricefields:
            if price in newv:
                if action == 'SELL' and price == 'fee':
                    newv[price] = fixup_price(newv['date'], 'USD', newv[price], change_sign=True)
                else:
                    newv[price] = fixup_price(newv['date'], 'USD', newv[price])
        if action == 'SELL':
            newv['qty'] = newv['qty'] * -1
        newv['source'] = f'schwab:{filename}'
        logger.debug('Processing record: %s', newv)

        newlist.append(newv)

    sorted_transactions = sorted(newlist, key=lambda d: d['date'])
    return Transactions(transactions=sorted_transactions)
