"""
ESPPv2 main entry point
"""

# pylint: disable=invalid-name
import logging
import zipfile
from io import BytesIO
from decimal import Decimal
from typing import Tuple, NamedTuple
import datetime
from math import isclose
import simplejson as json
from espp2.console import console
from espp2.positions import Positions, InvalidPositionException
from espp2.transactions import normalize
from espp2.datamodels import (
    TaxReport,
    Transactions,
    Wires,
    Holdings,
    ForeignShares,
    TaxSummary,
    CreditDeduction,
)
from espp2.report import print_ledger, print_cash_ledger, print_report_holdings
from espp2.portfolio import Portfolio

logger = logging.getLogger(__name__)


class TaxReportReturn(NamedTuple):  # inherit from typing.NamedTuple
    report: TaxReport
    holdings: Holdings
    excel: bytes
    summary: TaxSummary


class ESPPErrorException(Exception):
    """ESPP Error Exception"""


def json_load(fp):
    """Load json file"""
    data = json.load(fp, parse_float=Decimal, encoding="utf-8")
    return data


def tax_report(  # noqa: C901
    year: int,
    broker: str,
    transactions: Transactions,
    wires: Wires,
    prev_holdings: Holdings,
    portfolio_engine: bool,
    verbose: bool = False,
    feature_flags=[],
) -> Tuple[TaxReport, Holdings, TaxSummary]:
    """Generate tax report"""

    this_year = [t for t in transactions.transactions if t.date.year == year]

    # Run the chosen tax calculation engine
    portfolio = Portfolio(
        year, broker, this_year, wires, prev_holdings, verbose, feature_flags
    )
    if portfolio_engine is False:
        p = Positions(year, prev_holdings, this_year, wires)
        p.process()
    else:
        p = portfolio

    holdings = p.holdings(year, broker)
    assert holdings.year == year
    report = {}

    fundamentals = p.fundamentals()
    if prev_holdings:
        report["prev_holdings"] = prev_holdings

    report["ledger"] = p.ledger.entries

    # End of Year Balance (formueskatt)
    try:
        prev_year_eoy = p.eoy_balance(year - 1)
        this_year_eoy = p.eoy_balance(year)
    except InvalidPositionException as err:
        logger.error(err)
        raise

    report["eoy_balance"] = {year - 1: prev_year_eoy, year: this_year_eoy}
    logger.info("Previous year eoy: %s", prev_year_eoy)
    logger.info("This tax year eoy: %s", this_year_eoy)
    try:
        report["dividends"] = p.dividends()
    except InvalidPositionException as err:
        logger.error(err)
        raise

    # Move these to different part of report. "Buys" and "Sales" in period
    # Position changes?
    report["buys"] = p.buys()
    report["sales"] = p.sales()
    fees = p.fees()
    if fees:
        logger.error("Unhandled fees: %s", fees)

    # Cash and wires

    report["unmatched_wires"] = p.unmatched_wires_report
    report["cash_ledger"] = p.cash.ledger()
    cashsummary = p.cash_summary
    report["espp_extra_info"] = p.espp_extra_info()
    foreignshares = []

    for e in report["eoy_balance"][year]:
        tax_deduction_used = 0
        dividend_nok_value = 0
        dividend = [d for d in report["dividends"] if d.symbol == e.symbol]
        if dividend:
            assert len(dividend) == 1
            tax_deduction_used = dividend[0].tax_deduction_used
            dividend_nok_value = dividend[0].amount.nok_value

        try:
            sales = report["sales"][e.symbol]
        except KeyError:
            sales = []
        total_gain_nok = 0
        total_gain_post_tax_inc_nok = 0

        for s in sales:
            total_gain_nok += s.totals["gain"].nok_value
            if "post_tax_inc_gain" in s.totals:
                total_gain_post_tax_inc_nok += s.totals["post_tax_inc_gain"].nok_value
            tax_deduction_used += s.totals["tax_ded_used"]
            total_gain_nok -= s.totals["tax_ded_used"]
        if year == 2022:
            dividend_post_tax_inc_nok_value = 0
            if dividend:
                if dividend[0].post_tax_inc_amount:
                    dividend_post_tax_inc_nok_value = dividend[
                        0
                    ].post_tax_inc_amount.nok_value
                # dividend_post_tax_inc_nok_value = dividend[0].post_tax_inc_amount.nok_value
            foreignshares.append(
                ForeignShares(
                    symbol=e.symbol,
                    isin=fundamentals[e.symbol].isin,
                    country=fundamentals[e.symbol].country,
                    account=broker,
                    shares=e.qty,
                    wealth=e.amount.nok_value,
                    dividend=round(dividend_nok_value),
                    post_tax_inc_dividend=round(dividend_post_tax_inc_nok_value),
                    taxable_post_tax_inc_gain=round(total_gain_post_tax_inc_nok),
                    taxable_gain=round(total_gain_nok),
                    tax_deduction_used=round(tax_deduction_used),
                )
            )
        else:
            foreignshares.append(
                ForeignShares(
                    symbol=e.symbol,
                    isin=fundamentals[e.symbol].isin,
                    country=fundamentals[e.symbol].country,
                    account=broker,
                    shares=e.qty,
                    wealth=round(e.amount.nok_value),
                    dividend=round(dividend_nok_value),
                    taxable_gain=round(total_gain_nok),
                    tax_deduction_used=round(tax_deduction_used),
                )
            )

    # Tax paid in the US on dividends
    credit_deductions = []
    for e in report["dividends"]:
        expected_tax = Decimal(".15") * e.gross_amount.nok_value
        if not isclose(
            round(expected_tax, 2), round(abs(e.tax.nok_value), 2), rel_tol=0.0001
        ):
            logger.error(
                "Expected source tax: %s (%s) got: %s (%s)",
                expected_tax,
                e.gross_amount,
                abs(e.tax.nok_value),
                e.tax,
            )
        expected_tax = round(expected_tax, 0)
        credit_deductions.append(
            CreditDeduction(
                symbol=e.symbol,
                country="USA",
                income_tax=expected_tax,
                gross_share_dividend=round(e.gross_amount.nok_value),
                tax_on_gross_share_dividend=expected_tax,
            )
        )

    # Tax summary:
    # - Cash held in the US account
    # - Losses on cash transfer / wire

    summary = TaxSummary(
        year=year,
        foreignshares=foreignshares,
        credit_deduction=credit_deductions,
        cashsummary=cashsummary,
    )
    return TaxReportReturn(TaxReport(**report), holdings, portfolio.excel_data, summary)


# Merge transaction files
# - "Concatenate" transaction on year bounaries
# - Pickle and others represent sales differently so a simple "key" based deduplication fails
# - Prefer last file in list then fill in up to first complete year
# - Limit to two files?
def merge_transactions_old(transaction_files: list, broker: str) -> Transactions:
    """Merge transaction files"""
    sets = []
    for tf in transaction_files:
        t = normalize(tf, broker)
        t = sorted(t.transactions, key=lambda d: d.date)
        sets.append((t[0].date.year, t[-1].date.year, t))
    # Determine from which file to use for which year
    years = {}
    overlap_done = False
    sets = sorted(sets, key=lambda d: d[0])
    for i, s in enumerate(sets):
        for year in range(s[0], s[1] + 1):
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


def merge_transactions_old2(transaction_files: list, broker: str) -> Transactions:
    """Merge transaction files"""
    all_transactions = []
    years = {}
    # Put all transactions together
    for tf in transaction_files:
        t = normalize(tf, broker)
        all_transactions.extend(t.transactions)

    # Sort transactions
    all_transactions.sort(key=lambda d: d.date)

    # Remove duplicates
    seen = set()
    unique_transactions = []
    for transaction in all_transactions:
        if transaction.date.year not in years:
            years[transaction.date.year] = 0
        if transaction._crc not in seen:
            unique_transactions.append(transaction)
            seen.add(transaction._crc)
        else:
            print(f"Duplicate transaction: {transaction.id} 0x{transaction._crc:08x}")

    return Transactions(transactions=unique_transactions), years


def merge_transactions(transaction_files: list, broker: str) -> Transactions:
    """Merge transaction files"""
    all_transactions = []
    date_intervals = []
    years = {}
    # Put all transactions together
    for tf in transaction_files:
        t = normalize(tf, broker)
        # Add to date interval
        date_intervals.append((t.fromdate, t.todate))
        all_transactions.extend(t.transactions)

    # Sort date intervals by start date
    date_intervals.sort(key=lambda interval: interval[0])

    # Check if intervals are continuous and non-overlapping
    for i in range(1, len(date_intervals)):
        if date_intervals[i][0] <= date_intervals[i - 1][1]:
            raise ESPPErrorException(
                f"Date interval is overlapping: {date_intervals[i - 1][1]} is not before {date_intervals[i][0]}"
            )
        if date_intervals[i][0] != date_intervals[i - 1][1] + datetime.timedelta(
            days=1
        ):
            raise ESPPErrorException(
                f"Date interval is not continuous: {date_intervals[i - 1][1]} is not the day before {date_intervals[i][0]}"
            )

    all_transactions.sort(key=lambda d: d.date)

    # Find all years in transactions
    for transaction in all_transactions:
        if transaction.date.year not in years:
            years[transaction.date.year] = 0

    return Transactions(transactions=all_transactions), years


def generate_previous_year_holdings(
    broker, years, year, prev_holdings, transactions, portfolio_engine, verbose=False
):
    """Start from earliest year and generate taxes for every year until previous year."""

    holdings = prev_holdings
    for y in years:
        # Start from the year after the holdings year
        if holdings and y <= holdings.year:
            continue
        if y >= year:
            break
        this_year = [t for t in transactions.transactions if t.date.year == y]
        logger.info("Calculating tax for previous year: %s", y)

        if portfolio_engine:
            p = Portfolio(
                y, broker, this_year, Wires([]), holdings, verbose, feature_flags=[]
            )
        else:
            p = Positions(
                y, holdings, this_year, received_wires=Wires([]), generate_holdings=True
            )
            p.process()

        # Calculate taxes for the year
        holdings = p.holdings(y, broker)

        if verbose:
            print_ledger(y, p.ledger.entries, console)
            print_cash_ledger(y, p.cash.ledger(), console)
            print_report_holdings(holdings, console)

    # Return holdings for previous year
    if not holdings:
        # Empty list
        return Holdings(year=year - 1, broker="", stocks=[], cash=[])

    return holdings


def do_holdings(broker, transaction_files: list, year, verbose=False) -> Holdings:
    """Generate holdings file"""
    transactions, years = merge_transactions(transaction_files, broker)

    logger.info("Changes in holdings for previous year")
    holdings = generate_previous_year_holdings(
        broker, years, year, [], transactions, portfolio_engine=True, verbose=verbose
    )

    return holdings


def get_zipdata(files) -> bytes:
    """Get zip data"""
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for name, data in files:
            zip_file.writestr(name, data)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def do_taxes(
    broker,
    transaction_files: list,
    holdfile,
    wirefile,
    year,
    portfolio_engine,
    verbose=False,
    feature_flags=[],
) -> Tuple[TaxReport, Holdings, TaxSummary]:
    """Do taxes
    This function is run in two phases:
    1. Process transactions and older holdings to generate holdings for previous year
    2. Process transactions and holdings for previous year to generate taxes for current year

    If holdings file is specified already for previous year, the first phase is skipped.
    """
    wires = []
    prev_holdings: Holdings = None

    transactions, years = merge_transactions(transaction_files, broker)

    if broker != "morgan":
        if year + 1 not in years:
            logger.error(f"No transactions into the year after the tax year {year + 1}")

    if wirefile and not isinstance(wirefile, Wires):
        wires = json_load(wirefile)
        wires = Wires(wires)
        logger.info("Wires: read")
    elif wirefile:
        wires = wirefile

    if holdfile:
        prev_holdings = json_load(holdfile)
        prev_holdings = Holdings(**prev_holdings)
        logger.info("Holdings file read")

    if prev_holdings and prev_holdings.year != year - 1:
        raise ESPPErrorException("Holdings file for previous year not found")

    return tax_report(
        year,
        broker,
        transactions,
        wires,
        prev_holdings,
        portfolio_engine,
        verbose=verbose,
        feature_flags=feature_flags,
    )
