'''
ESPPv2 main entry point
'''

# pylint: disable=invalid-name
import logging
from decimal import Decimal
import simplejson as json
from rich.console import Console
from espp2.positions import Positions, Cash, InvalidPositionException, Ledger
from espp2.transactions import normalize
from espp2.datamodels import TaxReport, Transactions, Wires, Holdings, ForeignShares, TaxSummary, CreditDeduction
from espp2.report import print_ledger, print_cash_ledger, print_report_holdings
from typing import Tuple

logger = logging.getLogger(__name__)

class ESPPErrorException(Exception):
    '''ESPP Error Exception'''

def json_load(fp):
    '''Load json file'''
    data = json.load(fp, parse_float=Decimal, encoding='utf-8')
    return data

# def validate_holdings(broker, year, prev_holdings, transactions):
#     '''Validate holdings and filter transactions'''
#     if prev_holdings:
#         if broker != prev_holdings.broker:
#             raise ESPPErrorException(f'Broker mismatch: {broker} != {prev_holdings.broker}')
#     # # Remove duplicate transactions
#     # transactions = deduplicate(transactions)
#     if prev_holdings and prev_holdings.stocks and prev_holdings.year == year - 1:
#         # Filter out transactions from previous year
#         # TODO: Cash?
#         transactions = [t for t in transactions if t.date.year == year]
#         return prev_holdings, transactions

#     # No holdings, or holdings are from wrong year
#     c = Cash(year-1, transactions, None)
#     p = Positions(year-1, prev_holdings, transactions, c)
#     print('***Cash from previous year***')
#     print_cash_ledger(c.ledger(), Console())
#     holdings = p.holdings(year-1, broker)
#     transactions = [t for t in transactions if t.date.year == year]
#     return holdings, transactions

from typing import NamedTuple
class TaxReportReturn(NamedTuple):  # inherit from typing.NamedTuple
    report: TaxReport
    holdings: Holdings
    summary: TaxSummary


def tax_report(year: int, broker: str, transactions: Transactions, wires: Wires,
               prev_holdings: Holdings, verbose : bool = False) -> Tuple[TaxReport, Holdings, TaxSummary]:
    '''Generate tax report'''

    this_year = [t for t in transactions.transactions if t.date.year == year]
    p = Positions(year, prev_holdings, this_year, wires)
    p.process()
    holdings = p.holdings(year, broker)
    report = {}
    fundamentals = p.fundamentals()
    if prev_holdings:
        report['prev_holdings'] = prev_holdings
    report['ledger'] = p.ledger.entries

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
    fees = p.fees()
    if fees:
        logger.error("Unhandled fees: %s", fees)

    # Cash and wires

    report['unmatched_wires'] = p.unmatched_wires_report
    report['cash_ledger'] = p.cash.ledger()
    cashsummary = p.cash_summary

    foreignshares = []

    for e in report['eoy_balance'][year]:
        tax_deduction_used = 0
        dividend_nok_value = 0
        dividend = [d for d in report['dividends'] if d.symbol == e.symbol]
        if dividend:
            assert len(dividend) == 1
            tax_deduction_used = dividend[0].tax_deduction_used
            dividend_nok_value = dividend[0].amount.nok_value
        try:
            sales = report['sales'][e.symbol]
        except KeyError:
            sales = []
        total_gain_nok = 0
        total_gain_pre_tax_inc_nok = 0
        for s in sales:
            total_gain_nok += s.totals['gain'].nok_value
            total_gain_pre_tax_inc_nok += s.totals['pre_tax_inc_gain'].nok_value
            tax_deduction_used += s.totals['tax_ded_used']
        if year == 2022:
            dividend_pre_tax_inc_nok_value = 0
            if dividend:
                dividend_pre_tax_inc_nok_value = dividend[0].pre_tax_inc_amount.nok_value
            foreignshares.append(ForeignShares(symbol=e.symbol, isin=fundamentals[e.symbol].isin,
                                            country=fundamentals[e.symbol].country, account=broker,
                                            shares=e.qty, wealth=e.amount.nok_value,
                                            dividend=dividend_nok_value,
                                            pre_tax_inc_dividend=dividend_pre_tax_inc_nok_value,
                                            taxable_pre_tax_inc_gain=total_gain_pre_tax_inc_nok,
                                            taxable_gain=total_gain_nok,
                                            tax_deduction_used=tax_deduction_used))
        else:
            foreignshares.append(ForeignShares(symbol=e.symbol, isin=fundamentals[e.symbol].isin,
                                            country=fundamentals[e.symbol].country, account=broker,
                                            shares=e.qty, wealth=e.amount.nok_value,
                                            dividend=dividend_nok_value,
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
    return TaxReportReturn(TaxReport(**report), holdings, summary)

# Merge transaction files
# - "Concatenate" transaction on year bounaries
# - Pickle and others represent sales differently so a simple "key" based deduplication fails
# - Prefer last file in list then fill in up to first complete year
# - Limit to two files?
def merge_transactions(transaction_files: list) -> Transactions:
    '''Merge transaction files'''
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

    return Transactions(transactions=transactions), years


def generate_previous_year_holdings(broker, years, year, prev_holdings, transactions,
                                    verbose=False):
    '''Start from earliest year and generate taxes for every year until previous year.'''

    holdings = prev_holdings
    for y in years:
        if y >= year:
            break
        this_year = [t for t in transactions.transactions if t.date.year == y]
        logger.info('Calculating tax for previous year: %s', y)
        p = Positions(y, holdings, this_year, received_wires=Wires(__root__=[]))

        # Calculate taxes for the year
        p.process()
        holdings = p.holdings(y, broker)

        if verbose:
            print_ledger(p.ledger.entries, Console())
            print_cash_ledger(p.cash.ledger(), Console())
            print_report_holdings(holdings, Console())

    # Return holdings for previous year
    return holdings

def do_taxes(broker, transaction_files: list, holdfile,
             wirefile, year, verbose=False, opening_balance=None) -> Tuple[TaxReport, Holdings, TaxSummary]:
    '''Do taxes
    This function is run in two phases:
    1. Process transactions and older holdings to generate holdings for previous year
    2. Process transactions and holdings for previous year to generate taxes for current year

    If holdings file is specified already for previous year, the first phase is skipped.
    '''
    wires = []
    prev_holdings = []
    transactions, years = merge_transactions(transaction_files)

    if holdfile and opening_balance:
        raise ESPPErrorException('Cannot specify both opening balance and holdings file')

    if wirefile and not isinstance(wirefile, Wires):
        wires = json_load(wirefile)
        wires = Wires(__root__=wires)
        logger.info('Wires: read')
    elif wirefile:
        wires = wirefile

    if holdfile:
        prev_holdings = json_load(holdfile)
        prev_holdings = Holdings(**prev_holdings)
        logger.info('Holdings file read')
    elif opening_balance:
        prev_holdings = opening_balance

    if (prev_holdings and prev_holdings.year == year-1) or (not prev_holdings and year in years):
        # Phase 2
        # Previous holdings or all transactions from the tax year (new user)
        logger.info('Holdings file for previous year found, calculating tax')
        return tax_report(
            year, broker, transactions, wires, prev_holdings, verbose=verbose)

    # Phase 1. Return our approximation for previous year holdings for review
    logger.info('Changes in holdings for previous year')
    return generate_previous_year_holdings(broker, years, year, prev_holdings, transactions, verbose)
