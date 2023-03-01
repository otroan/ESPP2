# Use Rich tables to print the tax reports

from decimal import Decimal
from rich.console import Console
from rich.table import Table
from espp2.datamodels import TaxReport, Holdings

def print_report_dividends(report: TaxReport, console:Console):

    table = Table(title="Dividends:")
    table.add_column("Symbol", justify="right", style="cyan", no_wrap=True)
    table.add_column("Dividend", justify="right", style="black", no_wrap=True)
    table.add_column("Tax", style="magenta")
    table.add_column("Tax Deduction Used (NOK)", style="magenta")

    for d in report.dividends:
        table.add_row(d.symbol, f'{d.amount.nok_value}  ${d.amount.value}',
                      f'{d.tax.nok_value}  ${d.tax.value}',
                      str(d.tax_deduction_used))
    console.print(table)


def print_report_unmatched_wires(report: TaxReport, console:Console):

    table = Table(title="Unmatched wires:")
    table.add_column("Date", justify="right", style="cyan", no_wrap=True)
    table.add_column("Amount", justify="right", style="black", no_wrap=True)
    table.add_column("Amount NOK", style="magenta")

    for w in report.unmatched_wires:
        table.add_row(str(w.date), str(w.amount.value), str(w.amount.nok_value))
    console.print(table)


def print_report_sales(report: TaxReport, console: Console):
    table = Table(title="Sales",
                  show_header=True, header_style="bold magenta")
    table.add_column("Symbol", justify="right", style="cyan", no_wrap=True)
    table.add_column("Qty", justify="right", style="magenta")
    table.add_column("Sale Date", justify="right", style="green")
    table.add_column("Sales Price", justify="right", style="green")
    table.add_column("Gain/Loss", justify="right", style="green")
    table.add_column("Buy Positions", justify="right", style="green")


    # table.add_column("Tax Deduction", justify="right", style="green")
    # table.add_column("Total", justify="right", style="black")
    symbol = None
    total = Decimal(0)
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
    # for i, e in enumerate(holdings.stocks):
    #     symbol = e.symbol
    #     total += e.qty
    #     table.add_row(e.symbol, str(e.qty), str(e.date), str(e.purchase_price), str(e.tax_deduction))
    #     if i+1 >= len(holdings.stocks) or holdings.stocks[i+1].symbol != symbol:
    #         table.add_row("", "", "", "", "", str(total))
    #         total = Decimal(0)

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


def print_report(report: TaxReport, holdings: Holdings):
    console = Console()

    # Print previous year holdings
    print_report_holdings(report.prev_holdings, console)

    for symbols in report.ledger:
        table = Table(title="Ledger: " + symbols)
        table.add_column("Date", justify="right", style="cyan", no_wrap=True)
        table.add_column("Symbol", justify="right", style="black", no_wrap=True)
        table.add_column("Adjust", style="magenta")
        table.add_column("Total", justify="right", style="green")

        for e in report.ledger[symbols]:
            table.add_row(str(e[0]), symbols, str(e[1]), str(e[2]))
        console.print(table)

    print_report_sales(report, console)
    print_report_dividends(report, console)
    # Print current year holdings
    print_report_holdings(holdings, console)


    print_report_unmatched_wires(report, console)
