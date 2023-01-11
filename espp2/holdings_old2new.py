#!/usr/bin/env python3

'''Convert old style holdings file to new.'''

import json
import sys
from fmv import FMV
import pandas as pd

# {'symbol': 'CSCO', 'date': '2021-05-12 00:00+0000', 'qty': 19.0, 'price': 53.43, 'amount': nan, 'price_nok': 442.07447699999994, 'tax_deduction': 2.210372385}
currency_converter = FMV()
def fixup_price(datestr, currency, pricestr):
    '''Fixup price.'''
    price = pd.to_numeric(pricestr.replace('$', '').replace(',', ''))
    exchange_rate = currency_converter.get_currency(currency, datestr)
    return {'currency': currency, "value": price, 'nok_exchange_rate': exchange_rate}


with open(sys.argv[1], 'r') as f:
    old_holdings = json.load(f)

new_stocks = []
for s in old_holdings['stocks']:
    print('S', s)
    entry = {}
    entry['symbol'] = s['symbol']
    entry['date'] = pd.to_datetime(s['date'], utc=True).strftime('%Y-%m-%d')
    entry['qty'] = s['qty']
    entry['tax_deduction'] = s['tax_deduction']
    entry['purchase_price'] = {'currency': 'USD', 'value': s['price'], 'nok_exchange_rate': s['price_nok'] / s['price'], 'nok_value': s['price_nok']}
    new_stocks.append(entry)

old_holdings['stocks'] = new_stocks
old_holdings['year'] = int(sys.argv[3])
old_holdings['broker'] = sys.argv[4]

with open(sys.argv[2], 'w') as f:
    json.dump(old_holdings, f, indent=4)

