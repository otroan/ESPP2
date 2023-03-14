'''
ESPPv2 main entry point
'''

# pylint: disable=invalid-name
import logging
from decimal import Decimal
from importlib.resources import files
import simplejson as json
from rich.console import Console
from espp2.positions import Positions, Cash, InvalidPositionException, Ledger
from espp2.transactions import normalize
from espp2.datamodels import TaxReport, Transactions, Wires, Holdings, ForeignShares, TaxSummary, CreditDeduction
from espp2.report import print_ledger
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
# def deduplicate(transactions):
#     '''Remove duplicate transactions'''
#     # Remove duplicate transactions
#     prededup = len(transactions)
#     seen = set()
#     transactions = [t for t in transactions if t.id not in seen and not seen.add(t.id)]
#     logger.debug('Transaction deduplication %s %s (before/after)', prededup, len(transactions))
#     return transactions

def validate_holdings(broker, year, prev_holdings, transactions):
    '''Validate holdings and filter transactions'''
    if prev_holdings:
        if broker != prev_holdings.broker:
            raise ESPPErrorException(f'Broker mismatch: {broker} != {prev_holdings.broker}')
    # # Remove duplicate transactions
    # transactions = deduplicate(transactions)
    if prev_holdings and prev_holdings.stocks and prev_holdings.year == year - 1:
        # Filter out transactions from previous year
        transactions = [t for t in transactions if t.date.year == year]
        return prev_holdings, transactions

    # No holdings, or holdings are from wrong year
    c = Cash(year-1, transactions, None)
    p = Positions(year-1, taxdata, prev_holdings, transactions, c)
    holdings = p.holdings(year-1, broker)
    transactions = [t for t in transactions if t.date.year == year]
    return holdings, transactions


def tax_report(year: int, broker: str, transactions: Transactions, wires: Wires,
               prev_holdings: Holdings, taxdata, verbose : bool = False) -> Tuple[TaxReport, Holdings, TaxSummary]:
    '''Generate tax report'''

    if verbose:
        l = Ledger(prev_holdings, transactions.transactions)
        console = Console()
        print_ledger(l.entries, console)

    holdings, transactions = validate_holdings(broker, year, prev_holdings, transactions.transactions)
    l = Ledger(holdings, transactions)

    c = Cash(year, transactions, wires)
    p = Positions(year, taxdata, holdings, transactions, c, ledger=l)

    report = {}
    fundamentals = p.fundamentals()
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
    # report['cash'] = {}
    report['cash_ledger'] = c.ledger()
    cashsummary = c.process()


    foreignshares = []

    for e in report['eoy_balance'][year]:
        dividend = [d for d in report['dividends'] if d.symbol == e.symbol]
        assert len(dividend) == 1
        tax_deduction_used = dividend[0].tax_deduction_used
        try:
            sales = report['sales'][e.symbol]
        except KeyError:
            sales = []
        total_gain_nok = 0
        for s in sales:
            total_gain_nok += s.totals['gain'].nok_value
            tax_deduction_used += s.totals['tax_ded_used']
        
        foreignshares.append(ForeignShares(symbol=e.symbol, isin=fundamentals[e.symbol].isin,
                                           country=fundamentals[e.symbol].country, account=broker,
                                           shares=e.qty, wealth=e.amount.nok_value,
                                           dividend=dividend[0].amount.nok_value,
                                           taxable_gain=total_gain_nok,
                                           tax_deduction_used=tax_deduction_used))

    # Tax paid in the US on dividends
    credit_deductions = []
    for e in report['dividends']:
        credit_deductions.append(CreditDeduction(symbol=e.symbol, country='USA',
                                                 income_tax=e.tax.nok_value,
                                                 gross_share_dividend=e.amount.nok_value,
                                                 tax_on_gross_share_dividend=e.tax.nok_value))

    # Tax summary:
    # - Cash held in the US account
    # - Losses on cash transfer / wire

    summary = TaxSummary(year=year, foreignshares=foreignshares, credit_deduction=credit_deductions,
                         cashsummary=cashsummary)
    return TaxReport(**report), p.holdings(year, broker), summary

# Merge transaction files
# - "Concatenate" transaction on year bounaries
# - Pickle and others represent sales differently so a simple "key" based deduplication fails
# - Prefer last file in list then fill in up to first complete year
# - Limit to two files?
def merge_transactions(transaction_files: list) -> Transactions:
    '''Merge transaction files'''

    # Single file, no need to merge
    if len(transaction_files) == 1:
        t = normalize(transaction_files[0])
        t = sorted(t.transactions, key=lambda d: d.date)
        return Transactions(transactions=t)
    if len(transaction_files) > 2:
        raise ESPPErrorException(f'Too many transaction files {len(transaction_files)}')

    sets = []
    for tf in transaction_files:
        t = normalize(tf)
        t = sorted(t.transactions, key=lambda d: d.date)
        sets.append((t[0].date.year, t[-1].date.year, t))
    # Determine from which file to use for which year
    years = {}
    overlap_done = False
    sets = sorted(sets, key=lambda d: d[0])
    for i, s in enumerate(sets):
        for year in range(s[0], s[1]+1):
            if year in years and not overlap_done:
                # Jump over first year in second file
                overlap_done = True
                continue
            years[year] = i

    transactions = []
    for i in sorted(years.keys()):
        per_year_t = sets[years[i]][2]
        t = [t for t in per_year_t if t.date.year == i]
        transactions += t

    return Transactions(transactions=transactions)

def do_taxes(broker, transaction_files: list, holdfile,
             wirefile, year, verbose=False) -> Tuple[TaxReport, Holdings, TaxSummary]:
    '''Do taxes'''
    report = []
    wires = []
    prev_holdings = []
    transactions = merge_transactions(transaction_files)

    # l = Ledger(None, transactions.transactions)
    # for e in l.entries['CSCO']:
    #     print(f'{str(e[0])}\t{e[1]}\t{e[2]}')

    if wirefile and not isinstance(wirefile, Wires):
        wires = json_load(wirefile)
        wires = Wires(wires=wires)
        logger.info('Wires: read')
    elif wirefile:
        wires = wirefile

    if holdfile:
        prev_holdings = json_load(holdfile)
        prev_holdings = Holdings(**prev_holdings)
        logger.info('Holdings file read')
    report, holdings, summary = tax_report(
        year, broker, transactions, wires, prev_holdings, taxdata, verbose=verbose)
    return report, holdings, summary