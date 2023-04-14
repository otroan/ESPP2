# Use Rich tables to print the tax reports

from decimal import Decimal
from rich.console import Console
from rich.table import Table
from espp2.datamodels import TaxReport, TaxSummary, Holdings, EOYDividend
from espp2.positions import Ledger
from espp2.console import console

def print_report_dividends(dividends: list[EOYDividend], console:Console):
    '''Dividends'''
    table = Table(title="Dividends:")
    table.add_column("Symbol", justify="center", style="cyan", no_wrap=True)
    table.add_column("Dividend", justify="right", style="black", no_wrap=True)
    table.add_column("Tax", style="magenta", justify="right")
    table.add_column("Tax Deduction Used (NOK)", style="magenta", justify="right")

    for d in dividends:
        table.add_row(d.symbol, f'{d.amount.nok_value:.2f}  ${d.amount.value:.2f}',
                      f'{d.tax.nok_value:.2f}  ${d.tax.value:.2f}',
                      f'{d.tax_deduction_used:.2f}')
    console.print(table)

def print_cash_ledger(ledger: list, console: Console):
    '''Cash ledger'''
    table = Table(title="Cash Ledger:")
    table.add_column("Date", justify="center", style="cyan", no_wrap=True)
    table.add_column("Amount", justify="right", style="black", no_wrap=True)
    table.add_column("Amount NOK", style="magenta", justify="right")
    table.add_column("Description", style="black", justify="left")
    table.add_column("Total USD", style="magenta", justify="right")

    for e in ledger:
        table.add_row(str(e[0].date), f'{e[0].amount.value:.2f}',
                      f'{e[0].amount.nok_value:.2f}', e[0].description, f'{e[1]:.2f}')
    console.print(table)

def print_report_unmatched_wires(wires: list, console:Console):
    '''Unmatched wires'''
    table = Table(title="Unmatched wires:")
    table.add_column("Date", justify="center", style="cyan", no_wrap=True)
    table.add_column("Amount", justify="right", style="black", no_wrap=True)
    table.add_column("Amount NOK", style="magenta")

    for w in wires:
        table.add_row(str(w.date), f'{w.value:.2f}', f'{w.nok_value:.2f}')
    console.print(table)


def print_report_sales(report: TaxReport, console: Console):
    '''Sales report'''
    table = Table(title="Sales",
                  show_header=True, header_style="bold magenta")
    table.add_column("Symbol", justify="center", style="cyan", no_wrap=True)
    table.add_column("Qty", justify="right", style="magenta")
    table.add_column("Sale Date", justify="center", style="green")
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
                buy_positions.add_row(f'{b.qty:.2f}', f'{b.purchase_price:.2f}', f'{gain.nok_value:.2f}  ${gain.value:.2f}')
            buy_positions.add_row("")
            table.add_row(k, f'{e.qty:.2f}', str(e.date),
                          f'{e.amount.nok_value:.2f}  ${e.amount.value:.2f}',
                          f'{e.totals["gain"].nok_value:.2f}  ${e.totals["gain"].value:.2f}', buy_positions, style=style)
            first = False

    console.print(table)

def print_report_holdings(holdings: Holdings, console: Console):
    table = Table(title=f"Holdings: {holdings.broker} {holdings.year}",
                  show_header=True, header_style="bold magenta")
    table.add_column("Symbol", justify="center", style="cyan", no_wrap=True)
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
        table.add_row(e.symbol, f'{e.qty:.2f}', str(e.date), f'{e.purchase_price:.2f}', f'{e.tax_deduction:.2f}')
        if i+1 >= len(holdings.stocks) or holdings.stocks[i+1].symbol != symbol:
            table.add_row("", "", "", "", "", f'{total:.2f}')
            total = Decimal(0)

    console.print(table)

    '''Cash ledger'''
    table = Table(title=f"Cash Holdings {holdings.year}:")
    table.add_column("Date", justify="center", style="cyan", no_wrap=True)
    table.add_column("Amount", justify="right", style="black", no_wrap=True)
    table.add_column("Amount NOK", style="magenta", justify="right")
    table.add_column("Description", style="black", justify="left")
    table.add_column("Total", style="black")
    total = Decimal(0)

    for e in holdings.cash:
        total += e.amount.value

        table.add_row(str(e.date), f'{e.amount.value:.2f}',
                      f'{e.amount.nok_value:.2f}', e.description)
    table.add_row("", "", "", "", f'{total:.2f}')

    console.print(table)

def print_ledger(ledger: dict, console: Console):
    for symbols in ledger:
        table = Table(title=f"Ledger: {symbols}")
        table.add_column("Date", justify="center", style="cyan", no_wrap=True)
        table.add_column("Symbol", justify="center", style="black", no_wrap=True)
        table.add_column("Adjust", style="magenta", justify="right")
        table.add_column("Total", justify="right", style="green")

        for e in ledger[symbols]:
            table.add_row(str(e[0]), symbols, f'{e[1]:.2f}', f'{e[2]:.2f}')
        console.print(table)

def print_report_tax_summary(summary: TaxSummary, console: Console):
    '''Tax summary'''
    console.print(f'Tax Summary for {summary.year}:\n', style="bold magenta")
    table = Table(title="Finance -> Shares -> Foreign shares:", title_justify="left")
    table.add_column("Symbol", justify="center", style="cyan", no_wrap=True)
    table.add_column("ISIN", justify="center", style="cyan", no_wrap=True)
    table.add_column("Country", justify="center", style="black", no_wrap=True)
    table.add_column("Account Manager/bank", justify="center", style="magenta")
    table.add_column("Number of shares as of 31. December", style="magenta", justify="right")
    table.add_column("Wealth", style="magenta", justify="right")
    table.add_column("Taxable dividend", style="magenta", justify="right")
    if summary.year == 2022:
        table.add_column("Share of Taxable dividend after October 6", style="magenta", justify="right")
    table.add_column("Taxable gain/loss", style="magenta", justify="right")
    if summary.year == 2022:
        table.add_column("Share of Taxable gain/loss after October 6", style="magenta", justify="right")

    table.add_column("Risk-free return utilised", style="magenta", justify="right")

    # All shares that have been held at some point throughout the year
    for e in summary.foreignshares:
        dividend = e.dividend
        gain = e.taxable_gain
        if summary.year == 2022:
            table.add_row(e.symbol, e.isin, e.country, e.account, f'{e.shares:.2f}', f'{e.wealth}',
                        f'{dividend}', f'{e.post_tax_inc_dividend}', f'{gain}', f'{e.taxable_post_tax_inc_gain}',
                        f'{e.tax_deduction_used}')
        else:
            table.add_row(e.symbol, e.isin, e.country, e.account, f'{e.shares:.2f}', f'{e.wealth}',
                        f'{dividend}', f'{gain}',
                        f'{e.tax_deduction_used}')
    console.print(table)
    console.print()

    table = Table(title="Method in the event of double taxation -> Credit deduction / tax paid abroad:", title_justify="left")
    table.add_column("Symbol", justify="center", style="cyan", no_wrap=True)
    table.add_column("Country", justify="center", style="black", no_wrap=True)
    table.add_column("Income tax", style="magenta", justify="right")
    table.add_column("Gross share dividend", style="magenta", justify="right")
    table.add_column("Of which tax on gross share dividend", style="magenta", justify="right")

    # Tax paid in the US on dividends
    for e in summary.credit_deduction:
        table.add_row(e.symbol, e.country, f'{e.income_tax}',
                      f'{e.gross_share_dividend}', f'{e.tax_on_gross_share_dividend}')
    console.print(table)
    console.print()
    
    # Transfer gain/loss
    table = Table(title="Transfer gain/loss:", title_justify="left")
    table.add_column("Date", justify="center", style="cyan", no_wrap=True)
    table.add_column("Sent", justify="right", style="cyan", no_wrap=True)
    table.add_column("Received", justify="right", style="cyan", no_wrap=True)
    table.add_column("Gain", justify="right", style="cyan", no_wrap=True)
    for e in summary.cashsummary.transfers:
        table.add_row(str(e.date), f'{e.amount_sent}', f'{e.amount_received}', f'{e.gain}')
    gain = summary.cashsummary.gain
    table.add_row('', '', '', f'{gain}', style="bold green" if gain > 0 else "bold red")

    console.print(table)
    console.print()

    table = Table(title="Cash account balance:", title_justify="left")
    table.add_column("USD", justify="right", style="cyan", no_wrap=True)
    table.add_column("Wealth (NOK)", justify="right", style="cyan", no_wrap=True)
    usd = summary.cashsummary.remaining_cash.value
    nok = summary.cashsummary.remaining_cash.nok_value
    table.add_row(f'{usd:.2f}', f'{nok:.2f}')

    console.print(table)


def print_report(year: int, summary: TaxSummary, report: TaxReport,
                 holdings: Holdings, verbose: bool):
    '''Pretty print tax report to console'''

    if verbose:
        # Print previous year holdings
        if report.prev_holdings:
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
