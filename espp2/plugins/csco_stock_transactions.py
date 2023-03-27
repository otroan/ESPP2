'''
Cisco Stocks page Excel transaction history normalizer.
'''

# pylint: disable=invalid-name
# pylint: disable=no-name-in-module
# pylint: disable=no-self-argument

import math
from decimal import Decimal
import dateutil.parser as dt
from pandas import read_excel
from pydantic import parse_obj_as
from espp2.fmv import FMV
from espp2.datamodels import Transactions, Entry, EntryTypeEnum, Amount, Deposit, Sell
import simplejson as json
import re
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)

currency_converter = FMV()

def todate(datestr: str) -> datetime:
    '''Convert string to datetime'''
    return datetime.strptime(datestr, '%Y-%b-%d')

def stock_transactions_xls_import(fd, filename):
    '''Parse cisco stocks ESPP Purchases XLS file.'''

    # Extract the cash and stocks activity tables
    dfs = read_excel(fd, skiprows=6)
    records = dfs.to_dict(orient='records')
    transes=[]
    for t in records:
        if t['Date of Transaction'] == 'Total':
            break
        if t['Transaction Type'] != 'Lapse':
            continue
        d = Deposit(type=EntryTypeEnum.DEPOSIT,
            date=todate(t['Date of Transaction']),
            qty=t['Shares Distributed'],
            symbol='CSCO',
            description='RSU Vest',
            purchase_price=Amount(
                todate(t['Date of Transaction']), currency='USD', value=t['Sale Price/FMV']),
            source=f'csco_rsu:{filename}',
        )
        transes.append(d)
    return Transactions(transactions=sorted(transes, key=lambda d: d.date))

def read(fd, filename='') -> Transactions:
    '''Main entry point of plugin. Return normalized Python data structure.'''
    return stock_transactions_xls_import(fd, filename)
