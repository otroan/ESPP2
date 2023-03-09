# Use Rich tables to print the tax reports

from decimal import Decimal
from rich.console import Console
from rich.table import Table
from espp2.datamodels import TaxReport, TaxSummary, Holdings, EOYDividend
from espp2.positions import Ledger

def print_report_tax_summary(year: int, report: TaxReport, holdings: Holdings, console:Console):
    console.print('Finance -> Shares -> Foreign shares')
    '''
    Symbol
    Country
    Account Manager/bank
    Number of shares as of 31. December
    Wealth
    Taxable dividend
    Taxable gain
    Risk-free return utilised
    '''

    table = Table(title="Finance -> Shares -> Foreign shares:")
    table.add_column("Symbol", justify="right", style="cyan", no_wrap=True)
    table.add_column("Country", justify="right", style="black", no_wrap=True)
    table.add_column("Account Manager/bank", style="magenta")
    table.add_column("Number of shares as of 31. December", style="magenta")
    table.add_column("Wealth", style="magenta")
    table.add_column("Taxable dividend", style="magenta")
    table.add_column("Taxable gain", style="magenta")
    table.add_column("Risk-free return utilised", style="magenta")

    # All shares that have been held at some point throughout the year
    for e in report.eoy_balance[str(year)]:
        dividend = [d for d in report.dividends if d.symbol == e.symbol]
        assert len(dividend) == 1
        tax_deduction_used = dividend[0].tax_deduction_used
        try:
            sales = report.sales[e.symbol]
        except KeyError:
            sales = []
        total_gain_nok = 0
        for s in sales: 
            total_gain_nok += s.totals['gain'].nok_value
            tax_deduction_used += s.totals['tax_ded_used']
        table.add_row(e.symbol, "", "", str(e.qty), str(e.amount.nok_value), str(
            dividend[0].amount.nok_value), str(total_gain_nok), str(tax_deduction_used))
    console.print(table)

    table = Table(title="Method in the event of double taxation -> Credit deduction / tax paid abroad:")
    table.add_column("Symbol", justify="right", style="cyan", no_wrap=True)
    table.add_column("Country", justify="right", style="black", no_wrap=True)
    table.add_column("Income tax", style="magenta")
    table.add_column("Gross share dividend", style="magenta")
    table.add_column("Of which tax on gross share dividend", style="magenta")

    # Tax paid in the US on dividends
    for e in report.dividends:
        table.add_row(e.symbol, "", str(abs(e.tax.nok_value)), str(
            e.amount.nok_value), str(abs(e.tax.nok_value)))
    console.print(table)


def print_report_dividends(dividends: list[EOYDividend], console:Console):

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

def print_cash_ledger(cash: list, console: Console):
    table = Table(title="Cash Ledger:")
    table.add_column("Date", justify="right", style="cyan", no_wrap=True)
    table.add_column("Amount", justify="right", style="black", no_wrap=True)
    table.add_column("Amount NOK", style="magenta")

    for w in cash:
        table.add_row(str(w.date), str(w.amount.value), str(w.amount.nok_value))
    console.print(table)

def print_report_cash(wires: list, cash, console:Console):

    if wires:
        table = Table(title="Unmatched wires:")
        table.add_column("Date", justify="right", style="cyan", no_wrap=True)
        table.add_column("Amount", justify="right", style="black", no_wrap=True)
        table.add_column("Amount NOK", style="magenta")

        for w in wires:
            table.add_row(str(w.date), str(w.value), str(w.nok_value))
        console.print(table)

    if cash:

        print('TYPE:', type(cash))
        for k,v in cash.items():
            print('CASH:', k,v)

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

def print_report_tax_summary2(summary: TaxSummary, console:Console):
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



def print_report(year: int, summary: TaxSummary, report: TaxReport, holdings: Holdings):
    console = Console()

    # Print previous year holdings
    print_report_holdings(report.prev_holdings, console)

    print_ledger(report.ledger, console)

    print_report_sales(report, console)
    print_report_dividends(report.dividends, console)
    # Print current year holdings
    print_report_holdings(holdings, console)

    print_cash_ledger(report.cash_ledger, console)

    print_report_cash(report.unmatched_wires, report.cash, console)


    # print_report_tax_summary(year, report, holdings, console)
    print_report_tax_summary2(summary, console)
