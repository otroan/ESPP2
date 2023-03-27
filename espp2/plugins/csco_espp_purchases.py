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
from espp2.datamodels import Transactions, Entry, EntryTypeEnum, Amount, Deposit
import simplejson as json
import re
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)

currency_converter = FMV()

def todate(datestr: str) -> datetime:
    '''Convert string to datetime'''
    return datetime.strptime(datestr, '%Y-%b-%d')

def espp_purchases_xls_import(fd, filename):
    '''Parse cisco stocks ESPP Purchases XLS file.'''

    # Extract the cash and stocks activity tables
    dfs = read_excel(fd, skiprows=6)
    records = dfs.to_dict(orient='records')
    transes=[]
    for t in records:
        logger.debug('Processing %s', t)
        if t['Offering Date'] == 'Total':
            break
        d = Deposit(type=EntryTypeEnum.DEPOSIT,
                    date=todate(t['Purchase Date']),
                    qty=t['Shares Purchased'],
                    symbol='CSCO',
                    description='ESPP Purchase',
                    purchase_price=Amount(
                        todate(t['Purchase Date']), currency='ESPPUSD', value=t['Purchase Date FMV']),
                    source=f'csco_espp:{filename}',
                    )
        transes.append(d)
    return Transactions(transactions=transes)

def read(fd, filename='') -> Transactions:
    '''Main entry point of plugin. Return normalized Python data structure.'''
    return espp_purchases_xls_import(fd, filename)
