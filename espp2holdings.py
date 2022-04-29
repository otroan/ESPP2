#!/usr/bin/env python3

import logging
import json
import sys
from fmv import FMV
import pandas as pd

symbol = 'CSCO'

infile = sys.argv[1]
outfile = sys.argv[2]
year = sys.argv[3]

with open('taxdata.json', 'r') as jf:
    taxdata = json.load(jf)
tax_deduction_rate = taxdata['tax_deduction_rates'][year][0]

with open (infile, 'r') as f:
    espp_data = json.load(f)
stocks = []

f = FMV()
for item in espp_data:
    r = {'symbol': symbol, 'date': item['raw']['date'], 'qty': item['raw']['n'] - item['sold'],
         'price': item['raw']['vpd']}
    if year in item['ubenyttet']:
        current_deduction = item['ubenyttet'][year]
    else:
        current_deduction = 0
    price_nok = r['price'] * f.get_currency('USD', r['date'])
    r['tax_deduction'] = current_deduction + (price_nok * tax_deduction_rate)/100
    r['price_nok'] = price_nok
    d = pd.to_datetime(r['date'], utc=True)
    r['date'] = d.strftime('%Y-%m-%d %R%z')
    #r['date'] =  d #df['date'] = df['date'].apply(lambda x: x.strftime('%Y-%m-%d %R%z'))

    stocks.append(r)        
        
results = {'stocks': stocks, "cash": [{}]}
with open (outfile, 'w') as f:
    json.dump(results, f, indent=4)

'''
   {
        "type": "BUY",
        "symbol": "SPY",
        "date": "2021-07-30 18:07+0000",
        "qty": 0.878,
        "price": 438.9285,
        "amount": -385.58,
        "price_nok": 3853.8800157,
        "tax_deduction": 19.2694000785
    },
 '''