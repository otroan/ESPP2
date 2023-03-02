'''
ESPPv2 main entry point
'''

# pylint: disable=invalid-name
import logging
from decimal import Decimal
from importlib.resources import files
import simplejson as json
from espp2.positions import Positions, Cash, InvalidPositionException, Holdings, Ledger
from espp2.transactions import normalize
from espp2.datamodels import TaxReport, Transactions, Wires, Holdings
from typing import Tuple

logger = logging.getLogger(__name__)

class ESPPErrorException(Exception):
    '''ESPP Error Exception'''

def json_load(fp):
    '''Load json file'''
    data = json.load(fp, parse_float=Decimal, encoding='utf-8')
    return data

# Initialize the taxdata
taxdata_file = files('espp2').joinpath('taxdata.json')
with open(taxdata_file, 'r', encoding='utf-8') as jf:
    taxdata = json.load(jf)

# TODO: Include cash
def deduplicate(transactions):
    '''Remove duplicate transactions'''
    # Remove duplicate transactions
    seen = set()
    transactions = [t for t in transactions if t.id not in seen and not seen.add(t.id)]
    return transactions

def validate_holdings(broker, year, prev_holdings, transactions):
    '''Validate holdings and filter transactions'''
    if prev_holdings:
        if broker != prev_holdings.broker:
            raise ESPPErrorException(f'Broker mismatch: {broker} != {prev_holdings.broker}')
    # Remove duplicate transactions
    transactions = deduplicate(transactions)
    if prev_holdings and prev_holdings.stocks and prev_holdings.year == year - 1:
        # Filter out transactions from previous year
        transactions = [t for t in transactions if t.date.year == year]
        return prev_holdings, transactions

    # No holdings, or holdings are from wrong year
    c = Cash(year-1, transactions, None)
    p = Positions(year-1, taxdata, prev_holdings, transactions, c)
    holdings = p.holdings(year-1, 'dummy')
    transactions = [t for t in transactions if t.date.year == year]
    return holdings, transactions


def tax_report(year: int, broker: str, transactions: Transactions, wires: Wires,
               prev_holdings: Holdings, taxdata) -> Tuple[TaxReport, Holdings]:
    '''Generate tax report'''

    holdings, transactions = validate_holdings(broker, year, prev_holdings, transactions.transactions)
    l = Ledger(holdings, transactions)

    c = Cash(year, transactions, wires)
    p = Positions(year, taxdata, holdings, transactions, c, ledger=l)

    report = {}
    report['prev_holdings'] = holdings
    report['ledger'] = l.entries
    # End of Year Balance (formueskatt)
    try:
        prev_year_eoy = p.eoy_balance(year-1)
        this_year_eoy = p.eoy_balance(year)
    except InvalidPositionException as err:
        logger.error(err)
        raise
    report['eoy_balance'] = {year - 1: prev_year_eoy,
                             year: this_year_eoy}

    logger.info('Previous year eoy: %s', prev_year_eoy)
    logger.info('This tax year eoy: %s', this_year_eoy)
    try:
        report['dividends'] = p.dividends()
    except InvalidPositionException as err:
        logger.error(err)
        raise

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


def do_taxes(broker, transaction_files: list, holdfile,
             wirefile, year) -> Tuple[TaxReport, Holdings]:
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
        print('TRANSACTION FILE TYPE', type(t))
        try:
            trans.append(normalize(t))
            # trans.append(normalize(t['format'], t['fd']))
        except Exception as e:
            raise ESPPErrorException(f'{t.name}: {e}') from e

    transactions = trans[0]
    for t in trans[1:]:
        transactions.transactions += t.transactions
    transactions.transactions= sorted(transactions.transactions, key=lambda d: d.date)

    if wirefile:
        wires = json_load(wirefile)
        wires = Wires(wires=wires)
        logger.info('Wires: read')

    if holdfile:
        prev_holdings = json_load(holdfile)
        prev_holdings = Holdings(**prev_holdings)
        logger.info('Holdings file read')
    report, holdings = tax_report(year, broker, transactions, wires, prev_holdings, taxdata)
    return report, holdings