'''
Read a pickle-file and create a transactions-file
'''

# import sys
import pickle
import simplejson as json
from decimal import Decimal
from pprint import pprint    # Pretty-print objects for debugging
from espp2.datamodels import Transactions

# These are needed when unpickling 'espp.pickle' files, as such objects
# are present in pickle file, and needs to be created during loading.
import datetime
import codecs

# ESPP2 tools needed
from espp2.positions import Positions, Cash
from espp2.fmv import FMV

# Store all transaction records here
records = []

# Needed to establish exchange-rates
currency_converter = FMV()

#
# This class is responsible for loading the pickle-file. It is a
# sub-class of the 'pickle.Unpickler' class, and implements a function
# that allows two things:
#
#   1) Mapping the original module hierarchy in the ESPP v1 tool so
#      it gets re-created where this tool can easily access it
#   2) Explicitly allows creation of the objects that we expect to
#      encounter in pickle files from ESPP v1 tool - and nothing else
#
# The first point avoids the need to fully re-create the module
# hierarchy of the ESPP v1 tool, and the second point deals with
# security as it only allows the type of objects needed to re-create
# the pickle file object structure.
#
class UnpicklerESPP(pickle.Unpickler):
    '''A tailor-made pickle-file loader class for old ESPPData instance'''

    class ESPPData:
        '''The class to hold the old data from a 'espp.pickle' file'''
        def __init__(self):
            pass

    def find_class(self, module, name):
        # Allow importing the ESPPData class from the old modules 'esppdata'
        # and 'espp.esppdata', but place the data into the ESPPData class
        # in UnpicklerESPP where this tool has easy access to it.
        if module == "espp.esppdata" and name == 'ESPPData':
            return getattr(self, 'ESPPData')
        if module == 'esppdata' and name == 'ESPPData':
            return getattr(self, 'ESPPData')
        # Dates in the old pickle-files uses this
        if module == 'datetime' and name == 'date':
            return getattr(datetime, 'date')
        # Encoding through codecs.encode is somehow also needed
        if module == '_codecs' and name == 'encode':
            return getattr(codecs, 'encode')
        # All else we forbid, as a safeguard against malicious code
        errmsg = f"module '{module}' name '{name}' is denied"
        raise pickle.UnpicklingError(errmsg)

def add_string(rec, name, value):
    rec[name] = value

def add_date(rec, name, date):
    add_string(rec, name, date.strftime('%Y-%m-%d'))

def add_value(rec, name, value):
    rec[name] = value

def add_amount(rec, name, date, currency, amount):
    tmp = dict()
    add_string(tmp, 'currency', currency)
    add_value(tmp, "value", amount)

    datestr = date.strftime('%Y-%m-%d')
    exch_rate = currency_converter.get_currency(currency, datestr)
    add_value(tmp, 'nok_exchange_rate', exch_rate)
    add_value(tmp, 'nok_value', Decimal(exch_rate) * amount)
    rec[name] = tmp

def do_deposit(record):
    date = record['date']
    n = Decimal(str(record['n']))
    price = Decimal(f"{record['price']}")
    vpd = Decimal(f"{record['vpd']}")
    fee = Decimal(record['fee'])

    newrec = dict()

    add_date(newrec, 'date', date)
    add_string(newrec, 'type', 'DEPOSIT')
    add_string(newrec, 'symbol', 'CSCO')
    add_string(newrec, 'description', 'ESPP')  # TODO: Make sure it is so!
    add_value(newrec, 'qty', n)
    add_date(newrec, 'purchase_date', date)   # TODO: Which date?
    # add_string(newrec, 'subscription_date', 'TODO!')
    add_amount(newrec, 'subscription_fmv', date, 'USD', vpd)
    # add_amount(newrec, 'plan_purchase_price', 'TODO!')
    add_amount(newrec, 'purchase_price', date, 'USD', price)

    records.append(newrec)

def do_reinvest(record):
    # REINVEST {'date': datetime.date(2021, 7, 28), 'amount': 262.5, 'fee': 0.0}
    date = record['date']
    amount = Decimal(f"{record['amount']}")
    newrec = dict()

    add_date(newrec, 'date', date)
    add_string(newrec, 'type', 'DIVIDEND_REINV')
    add_string(newrec, 'symbol', 'CSCO')
    add_amount(newrec, 'amount', date, 'USD', amount)
    add_string(newrec, 'description', '')

    records.append(newrec)

def do_trans(record):
    date = record['date']
    fee = Decimal(f"{record['fee']}")
    n = Decimal(f"{record['n']}")
    price = Decimal(f"{record['price']}")

    newrec = dict()

    add_date(newrec, 'date', date)
    add_string(newrec, 'type', 'SELL')
    add_string(newrec, 'symbol', 'CSCO')
    add_value(newrec, 'qty', -n)
    add_value(newrec, 'description', '')
    add_amount(newrec, 'fee', date, 'USD', fee)
    add_amount(newrec, 'amount', date, 'USD', price)
    records.append(newrec)

def do_transfer(record):
    date = record['date']
    fee = Decimal(f"{record['fee']}")
    n = Decimal(record['n'])
    price = record['price']

    newrec = dict()

    add_date(newrec, 'date', date)
    add_string(newrec, 'type', 'TRANSFER')
    add_value(newrec, 'qty', -n)
    add_string(newrec, 'symbol', 'CSCO')
    # add_amount(newrec, 'amount', date, 'USD', price)
    # add_amount(newrec, 'fee', date, 'USD', fee)

    records.append(newrec)

def do_dividend(record):
    date = record['payDate']
    amount = Decimal(f"{record['amount']}")
    netto = record['netto']
    payDate = record['payDate']
    taxPercentage = record['taxPercentage']

    newrec = dict()

    add_date(newrec, 'date', date)
    add_string(newrec, 'type', 'DIVIDEND')
    add_string(newrec, 'symbol', 'CSCO')
    add_string(newrec, 'description', 'Credit')
    add_amount(newrec, 'amount', payDate, 'USD', amount)

    records.append(newrec)

def do_tax(record):
    date = record['date']
    amount = Decimal(record['amount'])

    newrec = dict()

    add_date(newrec, 'date', date)

    if amount < 0:
        add_string(newrec, 'type', 'TAXSUB')
    else:
        add_string(newrec, 'type', 'TAX')
    add_string(newrec, 'symbol', 'CSCO')
    add_string(newrec, 'description', 'Debit')
    add_amount(newrec, 'amount', date, 'USD', -amount)

    records.append(newrec)

def do_rsu(record):
    date = record['date']
    fee = Decimal(record['fee'])
    n = Decimal(record['n'])
    price = Decimal(f"{record['price']}")
    vpd = Decimal(f"{record['vpd']}")

    newrec = dict()

    add_date(newrec, 'date', date)
    add_string(newrec, 'type', 'DEPOSIT')
    add_string(newrec, 'symbol', 'CSCO')
    add_string(newrec, 'description', 'RS')
    add_value(newrec, 'qty', n)
    add_date(newrec, 'purchase_date', date)   # TODO: Which date?
    # add_string(newrec, 'subscription_date', 'TODO!')
    add_amount(newrec, 'subscription_fmv', date, 'USD', vpd)
    # add_amount(newrec, 'plan_purchase_price', 'TODO!')
    add_amount(newrec, 'purchase_price', date, 'USD', price)

    records.append(newrec)

def do_journal(record):
    pass

def do_wire(record):
    pass


def read(pickle_file, filename='', logger=None) -> Transactions:
    '''Main entry point of plugin. Return normalized Python data structure.'''
    global records

    records = []

    # Read the pickle-file
    p = UnpicklerESPP(pickle_file).load()

    # Print the data of the raw pickle-file data for debugging
    if False:
        print('Pickle-file dump:')
        pprint(p.__dict__)

    for key in sorted(p.rawData):
        # Simple sanity-check, first item in key must be a date object
        if not isinstance(key[0], datetime.date):
            raise Exception(f'Transaction key not starting with a date')

        rectype = key[1]
        record = p.rawData[key]

        if rectype == 'DEPOSIT':
            do_deposit(record)
            continue

        if rectype == 'REINVEST':
            do_reinvest(record)
            continue

        if rectype == 'DIVIDEND':
            do_dividend(record)
            continue

        if rectype == 'TAX':
            do_tax(record)
            continue

        if rectype == 'RSU' or rectype == 'PURCHASE':
            do_rsu(record)
            continue

        if rectype == 'TRANSFER':
            do_transfer(record)
            continue

        if rectype == 'TRANS':
            do_trans(record)
            continue

        if rectype == 'JOURNAL':
            do_journal(record)
            continue

        if rectype == 'FEE':
            # TODO MORTEN
            continue

        if rectype == 'WIRE':
            do_wire(record)
            continue
        raise ValueError(f'Error: Unexpected pickle-file record: {rectype}')

    for r in records:
        r['source'] = f'pickle:{filename}'
    sorted_transactions = sorted(records, key=lambda d: d['date'])
    return Transactions(transactions=sorted_transactions)

