'''
Schwab CSB normalizer.
'''

import csv
import pandas as pd
from decimal import Decimal
from fmv import FMV

def schwab_csv_import(csv_file):
    '''Parse Schwab CSV file.'''

    data = []

    with open(csv_file, encoding='utf-8') as csv_fd:
        reader = csv.reader(csv_fd)

        next(reader)
        header = next(reader)
        assert header == ['Date', 'Action', 'Symbol', 'Description',
                          'Quantity', 'Fees & Commissions', 'Disbursement Election', 'Amount']
        field = lambda x: header.index(x)
        data = []
        try:
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
                    data[-1]['subdata'].append({subheader[v].upper(): k for v, k in enumerate(row) if v != 0})
                    row = next(reader)
                    subheader = None
                data.append({header[v].upper(): k for v, k in enumerate(row)})
        except StopIteration:
            pass
        return data

def action_to_type(value):
    '''Normalize transaction type.'''
    action = {'Wire Transfer': 'WIRE',
         'Service Fee': 'FEE',
         'Deposit': 'DEPOSIT',  # DEPOSIT EQUITY / DEPOSIT CASH
         'Dividend': 'DIVIDEND',
         'Tax Withholding': 'TAX',
         'Tax Reversal': 'TAXSUB',
         'Dividend Reinvested': 'CASH',
         'Sale': 'SELL',
         'Journal': 'WIRE',
         }
    if value in action:
        return action[value]
    raise Exception(f'Unknown transaction entry {value}')

def fixup_date(datastr):
    '''Fixup date'''
    try:
        return pd.to_datetime(datastr, utc=True).strftime('%Y-%m-%d')
    except ValueError:
        return datastr

currency_converter = FMV()
def fixup_price(datestr, currency, pricestr):
    '''Fixup price.'''
    price = Decimal(pd.to_numeric(pricestr.replace('$', '').replace(',', '')))
    exchange_rate = currency_converter.get_currency(currency, datestr)
    return {'currency': currency, "value": price, 'nok_exchange_rate': exchange_rate, 'nok_value': price * exchange_rate }

def fixup_number(numberstr):
    '''Convert string to number.'''
    try:
        return float(numberstr)
    except ValueError:
        return ""

def get_espp_exchange_rate(date):
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
    return Decimal(espp[date])

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
                'TYPE': 'type',
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
        is_espp = True if action == 'DEPOSIT' and description == 'ESPP' else False
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
            newv['purchase_price'] = newv.pop('purchase_fmv')
            newv['purchase_price']['currency'] = 'ESPPUSD'
            exchange_rate = get_espp_exchange_rate(newv['purchase_date'])
            newv['purchase_price']['nok_exchange_rate'] = exchange_rate
            newv['purchase_price']['nok_value'] = exchange_rate * newv['purchase_price']['value']

        # for price in pricefields:
        #     if price in newv:
        #         newv[price] = fixup_price(date, 'USD', newv[price])

        newlist.append(newv)
    return newlist

def read(csv_file, logger):
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
        action = action_to_type(csv_item['ACTION'])
        description = csv_item['DESCRIPTION']
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
                newv[newkey] = action_to_type(data_item)
            else:
                newv[newkey] = data_item
        if 'subdata' in newv:
            if len(newv['subdata']) == 1:
                newv |= subdata(action, description, newv['date'], data_item)[0]
                newv.pop('subdata')
            else:
                newv[newkey] = subdata(action, description, newv['date'], data_item)

        for price in pricefields:
            if price in newv:
                newv[price] = fixup_price(newv['date'], 'USD', newv[price])
        if action == 'SELL':
            newv['qty'] = newv['qty'] * -1
        newlist.append(newv)
    return sorted(newlist, key=lambda d: d['date'])


    # for i, r in df.iterrows():
    #     if r.type == 'SELL':
    #         df.loc[i, 'price'] = r.amount / r.qty
    #     if r.type == 'DEPOSIT' and r.description == 'RS':
    #         assert(len(r.subdata) == 1)
    #         df.loc[i, 'price'] = r.subdata[0]['VEST FMV']
    #     if r.type == 'DEPOSIT' and r.description == 'ESPP':
    #         df.loc[i, 'price'] = r.subdata[0]['PURCHASE FMV']
    #     if r.type == 'DEPOSIT' and r.description == 'Div Reinv':
    #         df.loc[i, 'price'] = r.subdata[0]['PURCHASE PRICE']
    # df['qty'] = np.where(df['type'] == 'SELL', -1 * df['qty'], df['qty'])
