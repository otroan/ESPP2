'''
ESPPv2 main entry point
'''

import logging
from decimal import Decimal
from importlib.resources import files
import simplejson as json
from espp2.positions import Positions, Cash, InvalidPositionException, Holdings
from espp2.transactions import normalize
from espp2.datamodels import TaxReport, Transactions, Wires, Holdings

logger = logging.getLogger(__name__)

def json_load(fp):
    '''Load json file'''
    data = json.load(fp, parse_float=Decimal, encoding='utf-8')
    return data

# Initialize the taxdata
taxdata_file = files('espp2').joinpath('taxdata.json')
with open(taxdata_file, 'r', encoding='utf-8') as jf:
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

    # Move these to different part of report. "Buys" and "Sales" in period
    # Position changes?
    report['buys'] = p.buys()
    report['sales'] = p.sales()

    # Cash and wires
    nomatch = c.wire()
    report['unmatched_wires'] = nomatch
    report['cash'] = c.process()

    return TaxReport(**report), p.holdings(year, broker)

# TODO: Also include broker?
def do_taxes(broker, transaction_files: list, holdfile, wirefile, year) -> (TaxReport, Holdings):
    '''Do taxes'''
    trans = []
    report = []
    wires = []
    prev_holdings = []
    # logger.info(f'Doing taxes: {year} {format}')
    # logger.info(f'Transactions: {transfile.name}')
    # logger.info(f'Holdings: {holdfile.filename}')
    # logger.info(f'Wires: {wirefile.filename}')
    for t in transaction_files:
        try:
            trans.append(normalize(t['format'], t['fd']))
        except Exception as e:
            raise Exception(f'{t["name"]}: {e}')

    transactions = trans[0]
    for t in trans[1:]:
        transactions.transactions += t.transactions

    if wirefile:
        wires = json_load(wirefile)
        wires = Wires(wires=wires)
        logger.info('Wires: read')

    if holdfile:
        prev_holdings = json_load(holdfile)
        prev_holdings = Holdings(**prev_holdings)
        logger.info(f'Holdings file read')
    report, holdings = tax_report(year, broker, transactions, wires, prev_holdings, taxdata)
    return report, holdings