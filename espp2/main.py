'''
ESPPv2 main entry point
'''

import logging
from decimal import Decimal
from importlib.resources import files
import simplejson as json
from espp2.positions import Positions, Cash, Wires, InvalidPositionException, Holdings
from espp2.transnorm import normalize
from espp2.datamodels import TaxReport, Transactions, Wires, Holdings

logger = logging.getLogger(__name__)

def json_load(fp):
    '''Load json file'''
    data = json.load(fp, parse_float=Decimal, encoding='utf-8')
    return data

# Initialize the taxdata
taxdata_file = files('espp2').joinpath('taxdata.json')
with open(taxdata_file, 'r') as jf:
    taxdata = json.load(jf)

def tax_report(year: int, broker: str, transactions: Transactions, wires: Wires, prev_holdings: Holdings, taxdata) -> (dict, Holdings):
    '''Generate tax report'''

    c = Cash(year, transactions.transactions, wires)
    p = Positions(year, taxdata, prev_holdings, transactions.transactions, c)

    report = {}

    # End of Year Balance (formueskatt)
    try:
        prev_year_eoy = p.eoy_balance(year-1)
        this_year_eoy = p.eoy_balance(year)
    except InvalidPositionException as err:
        logger.error(err)
        return {}, {}
    report['eoy_balance'] = {year - 1: prev_year_eoy,
                             year: this_year_eoy}

    logger.info('Previous year eoy: %s', prev_year_eoy)
    logger.info('This tax year eoy: %s', this_year_eoy)
    try:
        report['dividends'] = p.dividends()
    except InvalidPositionException as err:
        logger.error(err)
        return {}, {}

    report['buys'] = p.buys()
    report['sales'] = p.sales()
    print('BUYS', report['buys'])
    # Cash and wires
    nomatch = c.wire()
    report['unmatched_wires'] = nomatch
    report['cash'] = c.process()

    return TaxReport(**report), p.holdings(year, broker)

# TODO: Also include broker?
def do_taxes(transfile, transformat, holdfile, wirefile, year):
    '''Do taxes'''
    trans = []
    report = []
    wires = []
    prev_holdings = []
    logger.info(f'Doing taxes: {year} {format}')
    logger.info(f'Transactions: {transfile.filename}')
    logger.info(f'Holdings: {holdfile.filename}')
    logger.info(f'Wires: {wirefile.filename}')

    try:
        trans_object, trans = normalize(transformat, transfile.file)
    except Exception as e:
        raise Exception(f'{transfile.filename}: {e}')

    logger.info('Transactions: {len(trans_object)} read')

    if wirefile.filename:
        wires = json_load(wirefile.file)
        wires = Wires(wires=wires)
        logger.info(f'Wires: read')

    if holdfile.filename:
        prev_holdings = json_load(holdfile.file)
        prev_holdings = Holdings(holdings=prev_holdings)
        logger.info(f'Holdings file read')
    broker = transformat ## TODO: This is not quite right
    report, holdings = tax_report(year, broker, trans_object, wires, prev_holdings, taxdata)
    return report, holdings