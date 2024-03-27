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
from espp2.positions import Positions, InvalidPositionException, Ledger
from espp2.transactions import normalize
from espp2.datamodels import (
    TaxReport,
    Transactions,
    Wires,
    Holdings,
    ForeignShares,
    TaxSummary,
    CreditDeduction,
    Sell,
    EntryTypeEnum,
    Amount,
    Buy,
)
from espp2.report import print_ledger, print_cash_ledger, print_report_holdings
from espp2.fmv import FMV, FMVTypeEnum, get_tax_deduction_rate
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
) -> Tuple[TaxReport, Holdings, TaxSummary]:
    """Generate tax report"""

    this_year = [t for t in transactions.transactions if t.date.year == year]

    # Run the chosen tax calculation engine
    portfolio = Portfolio(year, broker, this_year, wires, prev_holdings, verbose)
    if portfolio_engine is False:
        p = Positions(year, prev_holdings, this_year, wires)
        p.process()
    else:
        p = portfolio

    holdings = p.holdings(year, broker)
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
        expected_tax = round(Decimal(".15") * e.gross_amount.nok_value)
        if not isclose(expected_tax, abs(round(e.tax.nok_value)), abs_tol=0.05):
            logger.error(
                "Expected source tax: %s got: %s",
                expected_tax,
                abs(round(e.tax.nok_value)),
            )
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
def merge_transactions(transaction_files: list) -> Transactions:
    """Merge transaction files"""
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


def generate_previous_year_holdings(
    broker, years, year, prev_holdings, transactions, verbose=False
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

        p = Positions(
            y, holdings, this_year, received_wires=Wires([]), generate_holdings=True
        )

        # Calculate taxes for the year
        p.process()
        holdings = p.holdings(y, broker)

        if verbose:
            print_ledger(p.ledger.entries, console)
            print_cash_ledger(p.cash.ledger(), console)
            print_report_holdings(holdings, console)

    # Return holdings for previous year
    if not holdings:
        # Empty list
        return Holdings(year=year - 1, broker="", stocks=[], cash=[])

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
    transaction_file,
    holdfile,
    wirefile,
    year,
    portfolio_engine,
    verbose=False,
    opening_balance=None,
) -> Tuple[TaxReport, Holdings, TaxSummary]:
    """Do taxes
    This function is run in two phases:
    1. Process transactions and older holdings to generate holdings for previous year
    2. Process transactions and holdings for previous year to generate taxes for current year

    If holdings file is specified already for previous year, the first phase is skipped.
    """
    wires = []
    prev_holdings = []
    t = normalize(transaction_file)
    t = sorted(t.transactions, key=lambda d: d.date)
    transactions = Transactions(transactions=t)

    if holdfile and opening_balance:
        raise ESPPErrorException(
            "Cannot specify both opening balance and holdings file"
        )

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
    elif opening_balance:
        prev_holdings = opening_balance

    if prev_holdings and prev_holdings.year != year - 1:
        raise ESPPErrorException("Holdings file for previous year not found")

    return tax_report(year, broker, transactions, wires, prev_holdings, portfolio_engine, verbose=verbose)


def do_holdings_1(
    broker, transaction_files: list, holdfile, year, verbose=False, opening_balance=None
) -> Holdings:
    """Generate holdings file"""
    prev_holdings = []
    transactions, years = merge_transactions(transaction_files)

    if holdfile and opening_balance:
        raise ESPPErrorException(
            "Cannot specify both opening balance and holdings file"
        )

    if holdfile:
        prev_holdings = json_load(holdfile)
        prev_holdings = Holdings(**prev_holdings)
        logger.info("Holdings file read")
    elif opening_balance:
        prev_holdings = opening_balance

    logger.info("Changes in holdings for previous year")
    holdings = generate_previous_year_holdings(
        broker, years, year, prev_holdings, transactions, verbose
    )

    return holdings


def do_holdings_2(
    broker, transaction_files: list, year, expected_balance, verbose=False
) -> Holdings:
    """Calculate a holdings based on an expected balance and the ESPP and RSU transaction files"""

    transes = []

    for tf in transaction_files:
        t = normalize(tf)
        transes += t.transactions

    # Determine from which file to use for which year
    t = sorted(transes, key=lambda d: d.date)

    years = {}
    first = t[0].date.year
    last = t[-1].date.year
    years = {y: 0 for y in range(first, last + 1)}
    transactions = Transactions(transactions=t)

    # Phase 1. Return our approximation for previous year holdings for review
    logger.info("Changes in holdings for previous year")
    holdings = generate_previous_year_holdings(
        broker, years, year, None, transactions, verbose
    )
    logger.debug("Holdings for previous year: %s", holdings.json(indent=2))

    logger.info("Expected balance: %s", expected_balance)
    symbol = expected_balance.symbol
    qty = expected_balance.qty
    sum_qty = sum(e.qty for e in holdings.stocks if e.symbol == symbol)
    logger.info("Current balance: %s/%s", sum_qty, qty)
    if sum_qty != qty:
        logger.info("Artifically selling: %s", sum_qty - qty)
        sell_trans = Sell(
            type=EntryTypeEnum.SELL,
            symbol=symbol,
            qty=-(sum_qty - qty),
            date=datetime.date(year - 1, 12, 31),
            price=0.0,
            description="",
            amount=Amount(0),
            source="artificial",
        )
        transactions.transactions.append(sell_trans)
        t = sorted(transactions.transactions, key=lambda d: d.date)
        transactions = Transactions(transactions=t)
        holdings = generate_previous_year_holdings(
            broker, years, year, None, transactions, verbose
        )
    return holdings


def do_holdings_3(
    broker, transaction_file, year, expected_balance, verbose=False
) -> Holdings:
    """
    Calculate a holdings based on an expected balance and a single transaction file.
    This will only work if any position prior to the beginngin of the transaction file has been
    sold before the tax year
    """

    t = normalize(transaction_file)
    transes = t.transactions

    symbol = expected_balance.symbol
    qty = expected_balance.qty
    delta = 0
    ledger = Ledger(None, transes)
    buydate = None

    for s, entries in ledger.entries.items():
        total_shares = ledger.total_shares(s, datetime.date(year - 1, 12, 31))
        if s == symbol:
            delta = abs(total_shares - qty)
            buyyear = entries[0][0].year - 1
            buydate = datetime.date(buyyear, 1, 1)
            break

    if delta > 0:
        # Artifically buy the number of missing shares
        purchase_price = Amount(amountdate=buydate, currency="USD", value=0)
        buy_trans = Buy(
            type=EntryTypeEnum.BUY,
            symbol=symbol,
            qty=delta,
            date=buydate,
            description="Artifical Buy",
            purchase_price=purchase_price,
            source="artificial",
        )
        transes.insert(0, buy_trans)

    # Determine from which file to use for which year
    t = sorted(transes, key=lambda d: d.date)

    years = {}
    first = t[0].date.year
    last = t[-1].date.year
    years = {y: 0 for y in range(first, last + 1)}
    transactions = Transactions(transactions=t)

    logger.info("Expected balance: %s", expected_balance)
    logger.info("Current balance: %s/%s", delta, qty)
    holdings = generate_previous_year_holdings(
        broker, years, year, None, transactions, verbose
    )
    return holdings


def do_holdings_4(broker, transaction_file, year, verbose=False) -> Holdings:
    """Generate holdings file for Morgan"""

    assert year == 2022
    assert broker == "morgan"

    prev_holdings = []

    transactions = normalize(transaction_file)

    years = {}
    first = transactions.transactions[0].date.year
    last = transactions.transactions[-1].date.year
    years = {y: 0 for y in range(first, last + 1)}

    logger.info("Changes in holdings for previous year")
    holdings = generate_previous_year_holdings(
        broker, years, year, prev_holdings, transactions, verbose
    )

    #
    # Force tax-deduct reset. This is needed if the history is
    # incomplete and we can only make an assumption that tax-deduction
    # have been applied, and that we can't apply it a second time.
    # This is for the year 2021 specifically - to bootstrap holdings
    # for Morgan users. The cut-off date below is the exdate for
    # the last dividend payout in 2021: For held shares aquired after this
    # date, no shielding could have been claimed for 2021 tax, so
    # we bring the shielding forward in the holdings (for use next year).
    # For shares bought before the exdate, the dividend payout would have
    # consumed the shielding (if shielding tax-deduction was claimed), so
    # we can't safely assume any accumulated shielding for such shares
    #
    last_dividend_date = datetime.date(2021, 10, 4)
    tax_deduction_rate = get_tax_deduction_rate(year - 1) * Decimal("0.01")
    for x in holdings.stocks:
        assert x.symbol == "CSCO"
        if x.date >= last_dividend_date:
            tax_free_deduction = tax_deduction_rate * x.purchase_price.nok_value
            x.tax_deduction = tax_free_deduction
        else:
            x.tax_deduction = Decimal("0.00")

    return holdings


def preheat_cache():
    """Initialize caches"""
    today = datetime.date.today()
    symbol = "CSCO"
    f = FMV()

    with console.status(" [blue]Refreshing currency information") as status:
        f.refresh("USD", today, FMVTypeEnum.CURRENCY)
        status.update(status=" [blue]Fetching stocks information")
        f.refresh(symbol, today, FMVTypeEnum.STOCK)
        status.update(status=" [blue] Fetching dividends information")
        f.refresh(symbol, today, FMVTypeEnum.DIVIDENDS)
        status.update(status=" [blue] Fetching fundamentals information")
        f.refresh(symbol, today, FMVTypeEnum.FUNDAMENTALS)
