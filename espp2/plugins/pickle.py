'''
Read a pickle-file and create a transactions-file
'''

# pylint: disable=invalid-name, too-few-public-methods

import pickle
import logging
import datetime
import codecs
from pprint import pformat    # Pretty-print objects for debugging
from espp2.datamodels import Transactions, Amount, Deposit, EntryTypeEnum, Sell, Tax, Dividend_Reinv
from espp2.datamodels import Dividend, Taxsub, Wire, Fee, Transfer

logger = logging.getLogger(__name__)

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

def do_deposit(record, source):
    ''' DEPOSIT {'date': datetime.date(2021, 7, 28), 'n': 1, 'vpd': 26.25} '''
    return Deposit(type=EntryTypeEnum.DEPOSIT,
                   date=record['date'],
                   symbol='CSCO',
                   description='ESPP',
                   qty=record['n'],
                   purchase_date=record['date'],
                   purchase_price=Amount(amountdate=record['date'],
                                         currency='ESPPUSD', value=record['vpd']),
                   source=source)

def do_reinvest(record, source):
    ''' REINVEST {'date': datetime.date(2021, 7, 28), 'amount': 262.5, 'fee': 0.0} '''
    return Dividend_Reinv(type=EntryTypeEnum.DIVIDEND_REINV,
                          date=record['date'],
                          symbol='CSCO',
                          description='',
                          amount=Amount(amountdate=record['date'],
                                        currency='USD', value=record['amount']),
                          source=source)

def do_trans(record, source):
    '''Sale'''
    if record['n'] == 0:
        # Old pickle file has a bug where it sometimes has a zero quanity for sale. Ignore it.
        logger.warning("Zero quantity for sale, ignoring it: %s", record)
        return None
    return Sell(type=EntryTypeEnum.SELL,
                date=record['date'],
                symbol='CSCO',
                description='',
                qty=-record['n'],
                fee=Amount(amountdate=record['date'], currency='USD', value=-record['fee']),
                amount=Amount(amountdate=record['date'], currency='USD',
                              value=record['price'] * record['n']),
                source=source)


def do_transfer(record, source):
    '''Shares are transferred to another broker'''
    return Transfer(type=EntryTypeEnum.TRANSFER,
                    date=record['date'],
                    symbol='CSCO',
                    description='',
                    qty=-record['n'],
                    fee=Amount(amountdate=record['date'], currency='USD', value=-record['fee']),
                    source=source)

def do_dividend(record, source):
    ''' Dividends '''
    return Dividend(type=EntryTypeEnum.DIVIDEND,
                    date=record['payDate'],
                    symbol='CSCO',
                    description='',
                    amount_ps=Amount(amountdate=record['payDate'], currency='USD',
                                     value=record['amount']),
                    source=source)

def do_tax(record, source):
    ''' Dividend tax'''
    if record['amount'] >= 0:
        # This is a tax refund, so we need to add a new record with the
        # same date, but with a positive amount
        return Tax(type=EntryTypeEnum.TAX,
                   date=record['date'],
                   symbol='CSCO',
                   description='',
                   amount=Amount(amountdate=record['date'], currency='USD',
                                 value=-record['amount']),
                   source=source)

    return Taxsub(type=EntryTypeEnum.TAXSUB,
                    date=record['date'],
                    symbol='CSCO',
                    description='',
                    amount=Amount(amountdate=record['date'], currency='USD',
                                  value=record['amount']),
                    source=source)


def do_rsu(record, source):
    ''' RSU '''
    return Deposit(type=EntryTypeEnum.DEPOSIT,
                   date=record['date'],
                   symbol='CSCO',
                   description='RSU',
                   qty=record['n'],
                   purchase_date=record['date'],
                   purchase_price=Amount(amountdate=record['date'], currency='USD',
                                         value=record['vpd']),
                   source=source)

def do_wire(record, source):
    ''' {'date': datetime.date(2012, 12, 12), 'sent': 12805.27, 'received': 71975.86161600001,
         'fee': 25.0}'''
    # Sent & Received
    return Wire(type=EntryTypeEnum.WIRE,
                date=record['date'],
                description='RSU',
                fee=Amount(amountdate=record['date'], currency='USD', value=-record['fee']),
                amount=Amount(amountdate=record['date'], currency='USD', value=-record['sent']),
                source=source)

def do_fee(record, source):
    ''' FEE: {'date': datetime.date(2018, 7, 9), 'amount': 25.0} '''
    return Fee(type=EntryTypeEnum.FEE,
               date=record['date'],
               amount=Amount(amountdate=record['date'], currency='USD', value=-record['amount']),
               source=source)

methods = {
    'DEPOSIT': do_deposit,
    'REINVEST': do_reinvest,
    'DIVIDEND': do_dividend,
    'TAX': do_tax,
    'RSU': do_rsu,
    'PURCHASE': do_rsu,
    'WIRE': do_wire,
    'FEE': do_fee,
    'TRANSFER': do_transfer,
    'TRANS': do_trans,
    'JOURNAL': do_wire,
}

def read(pickle_file, filename='') -> Transactions:
    '''Main entry point of plugin. Return normalized Python data structure.'''
    records = []
    source = f'pickle:{filename}'

    # Read the pickle-file
    p = UnpicklerESPP(pickle_file).load()
    # Print the data of the raw pickle-file data for debugging
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug('Raw pickle-file data: %s', pformat(p.__dict__))

    for key in sorted(p.rawData):
        # Simple sanity-check, first item in key must be a date object
        if not isinstance(key[0], datetime.date):
            raise ValueError(f'Transaction key not starting with a date {key}')

        rectype = key[1]
        record = p.rawData[key]
        logger.debug('Processing record: %s', (rectype, record))

        try:
            records.append(methods[rectype](record, source))
        except KeyError as e:
            raise ValueError(f'Error: Unexpected pickle-file record: {rectype}') from e

    return Transactions(transactions=records)
