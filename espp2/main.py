'''
ESPPv2 main entry point
'''

import logging
from decimal import Decimal
from importlib.resources import files
import simplejson as json
from espp2.positions import Positions, Cash, Wires
from espp2.transnorm import normalize
import sys

logger = logging.getLogger(__name__)

def json_load(fp):
    '''Load json file'''
    data = json.load(fp, parse_float=Decimal, encoding='utf-8')
    return data

# Initialize the taxdata
taxdata_file = files('espp2').joinpath('taxdata.json')
with open(taxdata_file, 'r') as jf:
    taxdata = json.load(jf)

def tax_report(year, transactions, wires, prev_holdings, taxdata, log):
    '''Generate tax report'''

    p = Positions(year, taxdata, prev_holdings, transactions, log)
    c = Cash(year, transactions, wires)

    report = {}

    # End of Year Balance (formueskatt)
    prev_year_eoy = p.eoy_balance(year-1)
    this_year_eoy = p.eoy_balance(year)
    report['eoy_balance'] = {year - 1: prev_year_eoy,
                             year: this_year_eoy}

    report['dividends'] = p.dividends()
    report['buys'] = p.buys()
    report['sales'] = p.sales()

    # Cash and wires
    nomatch = c.wire()
    report['unmatched_wires'] = nomatch
    report['cash'] = c.process()

    # New holdings
    holdings = p.holdings(year, 'schwab')
    return report, holdings

class Log():
    '''Log class'''
    def __init__(self):
        self.logs = []

    def info(self, msg):
        '''Add status message'''
        self.logs.append(msg)

# TODO: Also include broker?
def do_taxes(transfile, transformat, holdfile, wirefile, year, log):
    '''Do taxes'''
    trans = []
    report = []
    wires = []
    prev_holdings = []
    log.info(f'Doing taxes: {year} {format}')
    log.info(f'Transactions: {transfile.filename}')
    log.info(f'Holdings: {holdfile.filename}')
    log.info(f'Wires: {wirefile.filename}')

    try:
        trans_object, trans = normalize(transformat, transfile.file, logger)
    except Exception as e:
        raise Exception(f'{transfile.filename}: {e}')

    log.info('Transactions: {len(trans_object)} read')

    if wirefile.filename:
        wires = json_load(wirefile.file)
        wires = Wires(wires=wires)
        log.info(f'Wires: read')

    if holdfile.filename:
        prev_holdings = json_load(holdfile.file)

    report, holdings = tax_report(year, trans, wires, prev_holdings, taxdata, log)
    return report, holdings