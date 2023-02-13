import csv
from decimal import Decimal
from espp2.fmv import FMV
import dateutil.parser as dt

def fixup_date(datestr):
    '''Fixup date'''
    d =  dt.parse(datestr)
    return d.strftime('%Y-%m-%d')

currency_converter = FMV()
def fixup_price(datestr, currency, pricestr, change_sign=False):
    '''Fixup price.'''
    price = Decimal(pricestr)
    # price = Decimal(pricestr.replace('$', '').replace(',', ''))
    if change_sign:
        price = price * -1
    exchange_rate = currency_converter.get_currency(currency, datestr)
    return {'currency': currency, "value": price, 'nok_exchange_rate': exchange_rate, 'nok_value': price * exchange_rate }

def fixup_number(numberstr):
    '''Convert string to number.'''
    try:
        return Decimal(numberstr)
    except ValueError:
        return ""

def td_csv_import(raw_data):
    '''Parse TD Ameritrade CSV file.'''

    data = []

    reader = csv.reader(raw_data)
    header = next(reader)
    assert header == ['DATE', 'TRANSACTION ID', 'DESCRIPTION', 'QUANTITY', 'SYMBOL', 'PRICE', 'COMMISSION', 'AMOUNT', 'REG FEE', 'SHORT-TERM RDM FEE', 'FUND REDEMPTION FEE', ' DEFERRED SALES CHARGE']
    field = lambda x: header.index(x)
    data = []
    try:
        while True:
            row = next(reader)
            if row[0] == '***END OF FILE***':
                break
            data.append({header[v].upper(): k for v, k in enumerate(row)})
    except StopIteration:
        pass
    return data

def action_to_type(value):
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

def read(raw_data, logger):
    '''Main entry point of plugin. Return normalized Python data structure.'''

    key_conv = {'DATE': 'date',
                'SYMBOL': 'symbol',
                'QUANTITY': 'qty',
                'PRICE': 'price',
                'COMMISSION': 'fee',
                'AMOUNT': 'amount',
                'DESCRIPTION': 'type',
                'TRANSACTION ID': 'transaction_id'
                }

    pricefields = ['amount', 'fee', 'price']
    numberfields = ['qty']

    csv_data = td_csv_import(raw_data)
    newlist = []
    for csv_item in csv_data:
        newv = {}
        action = action_to_type(csv_item['DESCRIPTION'])
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
                 newv['description'] = data_item
            else:
                newv[newkey] = data_item

        for pricefield in pricefields:
            if pricefield in newv:
                if action == 'SELL' and pricefield == 'fee':
                    newv[pricefield] = fixup_price(newv['date'], 'USD', newv[pricefield], change_sign=True)
                else:
                    newv[pricefield] = fixup_price(newv['date'], 'USD', newv[pricefield])
        if action == 'SELL':
            newv['qty'] = newv['qty'] * -1
        elif action == 'BUY':
            newv['purchase_price'] = newv.pop('price')
            # newv.pop('amount')

        newlist.append(newv)
    return sorted(newlist, key=lambda d: d['date'])
