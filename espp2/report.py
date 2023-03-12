# Use Rich tables to print the tax reports

from decimal import Decimal
from rich.console import Console
from rich.table import Table
from espp2.datamodels import TaxReport, TaxSummary, Holdings, EOYDividend
from espp2.positions import Ledger

def print_report_dividends(dividends: list[EOYDividend], console:Console):
    '''Dividends'''
    table = Table(title="Dividends:")
    table.add_column("Symbol", justify="right", style="cyan", no_wrap=True)
    table.add_column("Dividend", justify="right", style="black", no_wrap=True)
    table.add_column("Tax", style="magenta")
    table.add_column("Tax Deduction Used (NOK)", style="magenta")

    for d in dividends:
        table.add_row(d.symbol, f'{d.amount.nok_value}  ${d.amount.value}',
                      f'{d.tax.nok_value}  ${d.tax.value}',
                      str(d.tax_deduction_used))
    console.print(table)

def print_cash_ledger(ledger: list, console: Console):
    '''Cash ledger'''
    table = Table(title="Cash Ledger:")
    table.add_column("Date", justify="right", style="cyan", no_wrap=True)
    table.add_column("Amount", justify="right", style="black", no_wrap=True)
    table.add_column("Amount NOK", style="magenta", justify="right")
    table.add_column("Description", style="black")
    table.add_column("Total USD", style="magenta", justify="right")

    for e in ledger:
        table.add_row(str(e[0].date), str(e[0].amount.value),
                      str(e[0].amount.nok_value), e[0].description, str(e[1]))
    console.print(table)

def print_report_unmatched_wires(wires: list, console:Console):
    '''Unmatched wires'''
    table = Table(title="Unmatched wires:")
    table.add_column("Date", justify="right", style="cyan", no_wrap=True)
    table.add_column("Amount", justify="right", style="black", no_wrap=True)
    table.add_column("Amount NOK", style="magenta")

    for w in wires:
        table.add_row(str(w.date), str(w.value), str(w.nok_value))
    console.print(table)


def print_report_sales(report: TaxReport, console: Console):
    '''Sales report'''
    table = Table(title="Sales",
                  show_header=True, header_style="bold magenta")
    table.add_column("Symbol", justify="right", style="cyan", no_wrap=True)
    table.add_column("Qty", justify="right", style="magenta")
    table.add_column("Sale Date", justify="right", style="green")
    table.add_column("Sales Price", justify="right", style="green")
    table.add_column("Gain/Loss", justify="right", style="green")
    table.add_column("Buy Positions", justify="right", style="green")

    first = True

    for k, v in report.sales.items():
        for i, e in enumerate(v):
            if e.totals['gain'].value < 0:
                style = 'red'
            else:
                style = 'green'
            buy_positions = Table("qty", "price", "gain", show_edge=False, padding=0, show_header=first)
            for b in e.from_positions:
                gain = b.gain_ps * b.qty
                buy_positions.add_row(str(b.qty), str(b.purchase_price), f'{gain.nok_value}  ${gain.value}')
            buy_positions.add_row("")
            table.add_row(k, str(e.qty), str(e.date),
                          f'{e.amount.nok_value}  ${e.amount.value}',
                          f'{e.totals["gain"].nok_value}  ${e.totals["gain"].value}', buy_positions, style=style)
            first = False

    console.print(table)

def print_report_holdings(holdings: Holdings, console: Console):
    table = Table(title=f"Holdings: {holdings.broker} {holdings.year}",
                  show_header=True, header_style="bold magenta")
    table.add_column("Symbol", justify="right", style="cyan", no_wrap=True)
    table.add_column("Qty", justify="right", style="magenta")
    table.add_column("Purchase Date", justify="right", style="green")
    table.add_column("Purchase Price", justify="right", style="green")
    table.add_column("Tax Deduction", justify="right", style="green")
    table.add_column("Total", justify="right", style="black")
    symbol = None
    total = Decimal(0)
    for i, e in enumerate(holdings.stocks):
        symbol = e.symbol
        total += e.qty
        table.add_row(e.symbol, str(e.qty), str(e.date), str(e.purchase_price), str(e.tax_deduction))
        if i+1 >= len(holdings.stocks) or holdings.stocks[i+1].symbol != symbol:
            table.add_row("", "", "", "", "", str(total))
            total = Decimal(0)

    console.print(table)

def print_ledger(ledger: dict, console: Console):
    for symbols in ledger:
        table = Table(title=f"Ledger: {symbols}")
        table.add_column("Date", justify="right", style="cyan", no_wrap=True)
        table.add_column("Symbol", justify="right", style="black", no_wrap=True)
        table.add_column("Adjust", style="magenta")
        table.add_column("Total", justify="right", style="green")

        for e in ledger[symbols]:
            table.add_row(str(e[0]), symbols, str(e[1]), str(e[2]))
        console.print(table)

def print_report_tax_summary(summary: TaxSummary, console:Console):
    '''Tax summary'''
    console.print(f'Tax Summary for {summary.year}:', style="bold magenta")
    table = Table(title="Finance -> Shares -> Foreign shares:", title_justify="left")
    table.add_column("Symbol", justify="right", style="cyan", no_wrap=True)
    table.add_column("ISIN", justify="right", style="cyan", no_wrap=True)
    table.add_column("Country", justify="right", style="black", no_wrap=True)
    table.add_column("Account Manager/bank", style="magenta")
    table.add_column("Number of shares as of 31. December", style="magenta")
    table.add_column("Wealth", style="magenta")
    table.add_column("Taxable dividend", style="magenta")
    table.add_column("Taxable gain", style="magenta")
    table.add_column("Risk-free return utilised", style="magenta")

    # All shares that have been held at some point throughout the year
    for e in summary.foreignshares:
        table.add_row(e.symbol, e.isin, e.country, e.account, str(e.shares), str(e.wealth), str(
            e.dividend), str(e.taxable_gain), str(e.tax_deduction_used))
    console.print(table)

    table = Table(title="Method in the event of double taxation -> Credit deduction / tax paid abroad:", title_justify="left")
    table.add_column("Symbol", justify="right", style="cyan", no_wrap=True)
    table.add_column("Country", justify="right", style="black", no_wrap=True)
    table.add_column("Income tax", style="magenta")
    table.add_column("Gross share dividend", style="magenta")
    table.add_column("Of which tax on gross share dividend", style="magenta")

    # Tax paid in the US on dividends
    for e in summary.credit_deduction:
        table.add_row(e.symbol, e.country, str(e.income_tax),
                      str(e.gross_share_dividend), str(e.tax_on_gross_share_dividend))
    console.print(table)

    # Transfer gain/loss
    table = Table(title="Transfer gain/loss:", title_justify="left")
    table.add_column("Date", justify="right", style="cyan", no_wrap=True)
    table.add_column("Sent", justify="right", style="cyan", no_wrap=True)
    table.add_column("Received", justify="right", style="cyan", no_wrap=True)
    table.add_column("Gain", justify="right", style="cyan", no_wrap=True)
    for e in summary.cashsummary.transfers:
        table.add_row(str(e.date), str(e.amount_sent), str(e.amount_received), str(e.gain))
    gain = summary.cashsummary.gain
    table.add_row('', '', '', str(gain), style="bold green"if gain > 0 else "bold red")

    console.print(table)

    table = Table(title="Cash account balance:", title_justify="left")
    table.add_column("USD", justify="right", style="cyan", no_wrap=True)
    table.add_column("Wealth (NOK)", justify="right", style="cyan", no_wrap=True)
    usd = summary.cashsummary.remaining_cash.value
    nok = summary.cashsummary.remaining_cash.nok_value
    table.add_row(str(usd), str(nok))

    console.print(table)

def print_report(year: int, summary: TaxSummary, report: TaxReport, holdings: Holdings, verbose: bool):
    '''Pretty print tax report to console'''
    console = Console()

    if verbose:
        # Print previous year holdings
        print_report_holdings(report.prev_holdings, console)

        print_ledger(report.ledger, console)

        print_report_sales(report, console)
        print_report_dividends(report.dividends, console)
        # Print current year holdings
        print_report_holdings(holdings, console)

        print_cash_ledger(report.cash_ledger, console)


    if report.unmatched_wires:
        print_report_unmatched_wires(report.unmatched_wires, console)

    # print_report_tax_summary(year, report, holdings, console)
    print_report_tax_summary(summary, console)
