'''
ESPP portfolio class
'''

from copy import deepcopy
from io import BytesIO
from openpyxl import Workbook
from openpyxl.formatting import Rule
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.styles import Font, NamedStyle
from pydantic import BaseModel, ConfigDict, Field
from datetime import date
from decimal import Decimal
from IPython import embed
from espp2.datamodels import (
    Stock,
    Holdings,
    Amount,
    Sell,
    Dividend,
    Wires,
    Transactions,
    Dividend_Reinv,
    EOYBalanceItem,
    EOYDividend,
    TaxSummary,
    TaxReport,
    ForeignShares,
    CashSummary
)
from espp2.fmv import FMV, get_tax_deduction_rate

from espp2.cash import Cash
from typing import Any, ClassVar, Dict
from espp2.report import print_cash_ledger
from espp2.console import console

fmv = FMV()

def format_cells(ws, column, number_format):
    for cell in ws[column]:
        cell.number_format = number_format


class PortfolioPosition(BaseModel):
    """Stock positions"""

    symbol: str
    date: date
    qty: Decimal
    tax_deduction: Decimal = 0  # Total available tax deduction
    tax_deduction_acc: Decimal  # accumulated tax deduction from previous years
    tax_deduction_new: Decimal = 0  # tax deduction for this year
    purchase_price: Amount
    current_qty: Decimal = 0
    records: list[Any] = []
    coord: Dict[str, str] = {}

    def get_coord(self, key):
        return self.coord[key]
    def format(self, row, columns):
        '''Return a list of cells for a row'''
        l = [(row, columns.index("Symbol"), self.symbol)]
        l.append((row, columns.index("Date"), self.date))
        l.append((row, columns.index("Qty"), self.qty))
        l.append((row, columns.index("Price"),
                  f'={index_to_cell(row, columns.index("Price USD"))}*{index_to_cell(row, columns.index("Exchange Rate"))}'))
        self.coord['Price']= index_to_cell(row, columns.index("Price"))
        self.coord['Price USD']= index_to_cell(row, columns.index("Price USD"))
        l.append((row, columns.index("Price USD"), round(self.purchase_price.value, 2)))
        l.append((row, columns.index("Exchange Rate"), self.purchase_price.nok_exchange_rate))
        l.append((row, columns.index("Tax Ded Acc"), round(self.tax_deduction_acc, 2)))
        l.append((row, columns.index("Tax Ded Add"), round(self.tax_deduction_new, 2)))
        return l

class PortfolioDividend(BaseModel):
    """Stock dividends"""

    divdate: date
    qty: Decimal = Field(decimal_places=4)
    dividend_dps: Amount
    dividend: Amount
    tax_deduction_used: Decimal = 0
    tax_deduction_used_total: Decimal = 0
    parent: PortfolioPosition = None

    def format(self, row, columns):
        '''Return a list of cells for a row'''
        l = [(row, columns.index("Date"), self.divdate)]
        l.append((row, columns.index("Type"), "Dividend"))
        l.append((row, columns.index("iQty"), self.qty))
        l.append((row, columns.index("Exchange Rate"), self.dividend_dps.nok_exchange_rate))
        l.append((row, columns.index("Div PS"),
                  f'={index_to_cell(row, columns.index("Div PS USD"))}*{index_to_cell(row, columns.index("Exchange Rate"))}'))
        l.append((row, columns.index("Div PS USD"), round(self.dividend_dps.value, 2)))
        l.append((row, columns.index("Total Dividend"),
                  f'={index_to_cell(row, columns.index("Div PS"))}*{index_to_cell(row, columns.index("iQty"))}'))

        l.append((row, columns.index("Total Dividend USD"),
                  f'={index_to_cell(row, columns.index("Div PS USD"))}*{index_to_cell(row, columns.index("iQty"))}'))
        l.append((row, columns.index("Tax Ded Used"), round(self.tax_deduction_used, 2)))
        l.append((row, columns.index("Tax Ded Total"), round(self.tax_deduction_used_total, 2)))
        return l

class PortfolioSale(BaseModel):
    saledate: date
    qty: Decimal
    sell_price: Amount
    gain_ps: Amount
    gain: Amount
    total: Amount
    tax_deduction_used: Decimal = 0
    tax_deduction_used_total: Decimal = 0
    parent: PortfolioPosition = None

    def format(self, row, columns):
        l = [(row, columns.index("Date"), self.saledate)]
        l.append((row, columns.index("Type"), "Sale"))
        l.append((row, columns.index("Qty"), self.qty))
        l.append((row, columns.index("Price"),
                  f'={index_to_cell(row, columns.index("Price USD"))}*{index_to_cell(row, columns.index("Exchange Rate"))}'))
        l.append((row, columns.index("Price USD"), round(self.sell_price.value, 2)))
        l.append((row, columns.index("Exchange Rate"), self.sell_price.nok_exchange_rate))
        l.append((row, columns.index("Gain PS"),
                  f'={index_to_cell(row, columns.index("Price"))}-{self.parent.get_coord("Price")}'))

        l.append((row, columns.index("Gain PS USD"),
                    f'={index_to_cell(row, columns.index("Price USD"))}-{self.parent.get_coord("Price USD")}'))

        l.append((row, columns.index("Gain"),
                  f'={index_to_cell(row, columns.index("Gain PS"))}*ABS({index_to_cell(row, columns.index("Qty"))})'))
        l.append((row, columns.index("Gain USD"),
                  f'={index_to_cell(row, columns.index("Gain PS USD"))}*ABS({index_to_cell(row, columns.index("Qty"))})'))
        l.append((row, columns.index("Amount"),
                  f'=ABS({index_to_cell(row, columns.index("Price"))}*{index_to_cell(row, columns.index("Qty"))})'))
        l.append((row, columns.index("Amount USD"),
                  f'=ABS({index_to_cell(row, columns.index("Price USD"))}*{index_to_cell(row, columns.index("Qty"))})'))
        l.append((row, columns.index("Tax Ded Used"), round(self.tax_deduction_used, 2)))
        l.append((row, columns.index("Tax Ded Total"), round(self.tax_deduction_used_total, 2)))
        return l

def adjust_width(ws):
    def as_text(value):
        if value is None:
            return ""
        return str(value)

    # Adjust column width to fit the longest value in each column
    for column_cells in ws.columns:
        length = max(len(as_text(cell.value)) for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = length + 1

from openpyxl.utils import get_column_letter

def index_to_cell(row, column):
    """
    Convert a row and column index to an Excel cell reference.
    """
    column_letter = get_column_letter(column+1)
    return f"{column_letter}{row}"


class Portfolio:
    def buy(self, p):
        self.positions.append(
            PortfolioPosition(
                qty=p.qty,
                purchase_price=p.purchase_price,
                date=p.date,
                symbol=p.symbol,
                tax_deduction_acc=0,
                current_qty=p.qty,
            )
        )

    def dividend(self, transaction):
        '''Dividend'''
        shares_left = transaction.amount.value / transaction.dividend_dps
        total = transaction.amount.value
        for p in self.positions:
            if p.symbol == transaction.symbol:
                if p.current_qty == 0:
                    continue
                assert (
                    p.date <= transaction.exdate
                ), f"Exdate {transaction.exdate} before purchase date {p.date}"
                if p.current_qty >= shares_left:
                    shares_left = 0
                else:
                    shares_left -= p.current_qty

                used = transaction.dividend_dps * p.current_qty
                # used_nok = used * transaction.amount.nok_exchange_rate
                total -= used
                d = PortfolioDividend(
                    divdate=transaction.date,
                    qty=p.current_qty,
                    dividend_dps=Amount(
                        amountdate=transaction.date,
                        value=transaction.dividend_dps,
                        currency=transaction.amount.currency,
                    ),
                    dividend=Amount(
                        amountdate=transaction.date,
                        value=used,
                        currency=transaction.amount.currency,
                    ),
                    parent=p
                )
                p.records.append(d)
                if shares_left == 0:
                    break
        assert abs(total) < 1, f"Not all dividend used: {total}"
        self.cash.debit(transaction.date, transaction.amount, 'dividend')

    def tax(self, transaction):
        """
        TAX type=<EntryTypeEnum.TAX: 'TAX'> date=datetime.date(2022, 10, 26)
        symbol='CSCO' description='Debit' amount=NegativeAmount(currency='USD',
        nok_exchange_rate=Decimal('10.3171'), nok_value=Decimal('-167.446533'),
        value=Decimal('-16.23')) source='schwab:/Users/otroan/Stocks/erik/erik.csv'
        id='TAX 2022-10-26:7'
        """
        self.taxes.append(
            {
                "date": transaction.date,
                "symbol": transaction.symbol,
                "amount": transaction.amount,
            }
        )
        self.cash.credit(transaction.date, transaction.amount, 'tax')

    def dividend_reinv(self, transaction: Dividend_Reinv):
        self.cash.credit(transaction.date, transaction.amount, 'dividend reinvest')

    def sell(self, transaction):
        shares_to_sell = abs(transaction.qty)
        sell_price = Amount(
            amountdate=transaction.date,
            value=(transaction.amount.value - abs(transaction.fee.value))
            / abs(transaction.qty),
            currency=transaction.amount.currency,
        )
        for p in self.positions:
            sold = 0
            if p.symbol == transaction.symbol:
                if p.current_qty == 0:
                    continue
                if p.current_qty >= shares_to_sell:
                    p.current_qty -= shares_to_sell
                    sold = shares_to_sell
                    shares_to_sell = 0
                else:
                    sold = p.current_qty
                    shares_to_sell -= p.current_qty
                    p.current_qty = 0
                gain_ps = sell_price - p.purchase_price
                gain = (sell_price - p.purchase_price) * sold
                s = PortfolioSale(
                    saledate=transaction.date,
                    qty=-sold,
                    sell_price=sell_price,
                    gain_ps=gain_ps,
                    gain=gain,
                    # gain_ps=Amount(amountdate=transaction.date,
                    #                 value=gain_ps.value,
                    #                 currency=transaction.amount.currency),
                    # gain=Amount(amountdate=transaction.date,
                    #                 value=gain.value,
                    #                 currency=transaction.amount.currency),
                    total=sell_price * sold,
                    parent=p
                )
                p.records.append(s)
                if shares_to_sell == 0:
                    break
        self.cash.debit(transaction.date, transaction.amount.model_copy(), 'sale')
        self.cash.credit(transaction.date, transaction.fee.model_copy(), 'sale fee')

    def wire(self, transaction):
        # wire type=<EntryTypeEnum.WIRE: 'WIRE'>
        # date=datetime.date(2022, 5, 23)
        # amount=Amount(currency='USD', nok_exchange_rate=Decimal('9.6182'),
        # nok_value=Decimal('-310736.245402'), value=Decimal('-32307.11'))
        # description='Cash Disbursement' fee=NegativeAmount(currency='USD',
        # nok_exchange_rate=Decimal('9.6182'), nok_value=Decimal('-144.273000'),
        # value=Decimal('-15.00')) source='schwab:/Users/otroan/Stocks/erik/erik.csv'
        # id='WIRE 2022-05-23:3'
        pass

    def taxsub(self, transaction):
        self.cash.debit(transaction.date, transaction.amount, 'tax returned')

    dispatch = {
        "BUY": buy,
        "DEPOSIT": buy,
        "SELL": sell,
        # 'TRANSFER': 'transfer',
        "DIVIDEND": dividend,
        "DIVIDEND_REINV": dividend_reinv,
        "TAX": tax,
        "TAXSUB": taxsub,
        "WIRE": wire,
        # 'FEE': 'fee',
        # 'CASHADJUST': 'cashadjust',
    }
    # x = Portfolio(year, broker, transactions, wires, prev_holdings, verbose)

    def generate_tax_summary(self):
        # Generate foreign shares for tax report
        foreignshares = []
        credit_deduction = []
        # cashsummary = CashSummary()
        end_of_year = f'{self.year}-12-31'
        eoy_exchange_rate = fmv.get_currency('USD', end_of_year)

        for s in self.symbols:
            f = fmv.get_fundamentals2(s)
            total_qty = 0
            dividend_nok = 0
            taxable_gain = 0
            tax_deduction_used = 0
            for p in self.positions:
                if p.symbol != s or p.current_qty == 0:
                    continue
                total_qty += p.current_qty

            eoyfmv = fmv[s, end_of_year]
            wealth_nok = total_qty * eoyfmv * eoy_exchange_rate
            foreignshares.append(ForeignShares(symbol=p.symbol, isin=f.isin,
                                            country=f.country, account=self.broker,
                                            shares=total_qty, wealth=wealth_nok,
                                            dividend=dividend_nok,
                                            taxable_gain=taxable_gain,
                                            tax_deduction_used=tax_deduction_used))

        return TaxSummary(year=self.year, foreignshares=foreignshares,
                          credit_deduction=credit_deduction, cashsummary=self.cash_report)

    def eoy_balance_report(self, year):
        '''End of year summary of holdings'''
        assert year == self.year or year == self.year-1, f'Year {year} does not match portfolio year {self.year}'
        end_of_year = f'{year}-12-31'

        eoy_exchange_rate = fmv.get_currency('USD', end_of_year)
        r = []
        positions = self.positions if year == self.year else self.prev_holdings.stocks
        for symbol in self.symbols:
            total_shares = 0
            for p in positions:
                if p.symbol == symbol:
                    try:
                        total_shares += p.current_qty
                    except AttributeError:
                        total_shares += p.qty

            eoyfmv = fmv[symbol, end_of_year]
            r.append(EOYBalanceItem(symbol=symbol, qty=total_shares, amount=Amount(
                value=total_shares * eoyfmv, currency='USD',
                nok_exchange_rate=eoy_exchange_rate,
                nok_value=total_shares * eoyfmv * eoy_exchange_rate),
                fmv=eoyfmv))
        return r

    def generate_holdings(self):
        # Generate holdings for next year.
        holdings = []
        for p in self.positions:
            if p.current_qty == 0:
                continue
            hitem = Stock(date=p.date, symbol=p.symbol, qty=p.current_qty,
                          purchase_price=p.purchase_price, tax_deduction=p.tax_deduction)
            holdings.append(hitem)
        return Holdings(year=self.year, broker=self.broker, stocks=holdings, cash=[])

    def __init__(
        self,
        year: int,
        broker: str,
        transactions: Transactions,
        wires: Wires,
        holdings: Holdings,
        verbose: bool,
    ):
        self.year = year
        self.taxes = []
        self.positions = []
        self.cash = Cash(year=year)
        self.broker = broker

        self.column_headers = [
            "Symbol",
            "Date",
            "Type",
            "Qty",
            "iQty",
            "Price",
            "Price USD",
            "Exchange Rate",
            "Tax Ded Acc",
            "Tax Ded Add",
            "Gain PS",
            "Gain PS USD",
            "Gain",
            "Gain USD",
            "Amount",
            "Amount USD",
            "Div PS",
            "Div PS USD",
            "Total Dividend",
            "Total Dividend USD",
            "Tax Ded Used",
            "Tax Ded Total",
        ]

        self.prev_holdings = holdings
        if holdings:
            for p in holdings.stocks:
                try:
                    tax_deduction = p.tax_deduction
                except AttributeError:
                    tax_deduction = 0
                self.positions.append(
                    PortfolioPosition(
                        qty=p.qty,
                        purchase_price=p.purchase_price,
                        date=p.date,
                        symbol=p.symbol,
                        tax_deduction_acc=tax_deduction,
                        current_qty=p.qty,
                    )
                )

        # Process transactions.
        # There's a problem here. I need to add tax deduction before processing. But I can't do that because I don't know if I have a sale.
        # So I need to process sales first.
        for t in transactions:
            # Use dispatch to call a function per t.type
            self.__class__.dispatch[t.type](self, t)

        # Add tax deduction to the positions held by the end of the year
        total_tax_deduction = 0

        self.symbols = [p.symbol for p in self.positions]

        for p in self.positions:
            if p.current_qty > 0:
                tax_deduction_rate = get_tax_deduction_rate(self.year)
                tax_deduction = (
                    (p.purchase_price.nok_value + p.tax_deduction) * tax_deduction_rate
                ) / 100
                p.tax_deduction_new = tax_deduction
                print('POSITION THAT GETS TAX DEDUCTION FOR THIS YEAR', p.date, p.current_qty, p.symbol, p.tax_deduction_new)
            p.tax_deduction = p.tax_deduction_acc + p.tax_deduction_new
            total_tax_deduction += (p.tax_deduction * p.qty)

        print('Total tax deduction', total_tax_deduction)

        # Walk through and use the available tax deduction
        # Use tax deduction for dividend if we can. Then for sales. Then keep leftovers for next year.
        for p in self.positions:
            if p.tax_deduction > 0:
                # Walk through records looking for dividends
                for r in p.records:
                    if isinstance(r, PortfolioDividend):
                        if p.tax_deduction >= r.dividend_dps.nok_value:
                            p.tax_deduction -= r.dividend_dps.nok_value
                            r.tax_deduction_used = r.dividend_dps.nok_value
                            r.tax_deduction_used_total = (
                                r.dividend_dps.nok_value * r.qty
                            )
                        else:
                            r.tax_deduction_used = p.tax_deduction
                            r.tax_deduction_used_total = p.tax_deduction * r.qty
                            p.tax_deduction = 0
                    if isinstance(r, PortfolioSale) and r.gain_ps.nok_value > 0:
                        qty = abs(r.qty)
                        if p.tax_deduction >= r.gain_ps.nok_value:
                            p.tax_deduction -= r.gain_ps.nok_value
                            r.tax_deduction_used = r.gain_ps.nok_value
                            r.tax_deduction_used_total = r.gain_ps.nok_value * qty
                        else:
                            r.tax_deduction_used = p.tax_deduction
                            r.tax_deduction_used_total = p.tax_deduction * qty
                            p.tax_deduction = 0

        # Process wires
        db_wires = [t for t in transactions if t.type == 'WIRE']
        unmatched = self.cash.wire(db_wires, wires)
        self.unmatched_wires = unmatched
        print("Unmatched wires", unmatched)
        cash_report = self.cash.process()
        self.cash_report = cash_report
        print('CASH REPORT', cash_report)
        self.ledger = self.cash.ledger()
        print_cash_ledger(self.ledger, console)

        # Generate holdings for next year.
        self.eoy_holdings = self.generate_holdings()
        self.summary = self.generate_tax_summary()

        self.excel_data = self.excel_report()

    def excel_report(self):
        # Create an Excel workbook and get the active sheet
        year = self.year
        portfolio = self.positions
        workbook = Workbook()
        ws = workbook.active
        ws.title = f"Portfolio-{year}"
        # Extract column headers from the Stock Pydantic model

        # Write column headers to the Excel sheet
        ws.append(self.column_headers)
        ft = Font(bold=True)

        title_row = ws.row_dimensions[1]
        title_row.font = ft

        # Apply conditional formatting to change font color for negative numbers
        # dxf = DifferentialStyle(font=Font(color='FF0000'))
        ws.conditional_formatting.add(
            "C2:P50",
            CellIsRule(operator="lessThan", formula=["0"], font=Font(color="00FF0000")),
        )

        # Write data from Stock instances to the Excel sheet
        row = 2
        decimal_style = NamedStyle(name="decimal", number_format="0.00")
        for stock in portfolio:
            for row, col, value in stock.format(row, self.column_headers):
                ws.cell(row=row, column=col+1, value=value)
            row += 1
            for record in stock.records:
                for row, col, value in record.format(row, self.column_headers):
                    ws.cell(row=row, column=col+1, value=value)
                row += 1

        # Set number format for the entire column
        sum_cols = ["D", "L", "M", "N", "O", "Q", "R", "U"]
        l = len(ws[sum_cols[0]])
        for col in sum_cols:
            ws[f"{col}{l+1}"] = f"=SUM({col}2:{col}{l})"
            # format_cells(ws, col, number_format)

        # Tax (in a separate sheet?)
        # TODO: Include TAXSUB
        for t in self.taxes:
            ws.append(
                [
                    t["symbol"],
                    t["date"],
                    "Tax",
                    round(t["amount"].nok_value, 2),
                    round(t["amount"].value, 2),
                ]
            )

        adjust_width(ws)
        # Freeze the first row
        c = ws['A2']
        ws.freeze_panes = c

        # Separate sheet for cash
        ws = workbook.create_sheet("Cash")
        ws.append(["Date", "Description", "Amount", "Amount USD", "Total"])
        for c in self.ledger:
            ws.append([c[0].date, c[0].description, round(c[0].amount.nok_value, 2),
                       round(c[0].amount.value, 2), round(c[1], 2)])

        adjust_width(ws)

        # Separate sheet for EOY holdings
        ws = workbook.create_sheet("EOY Holdings")
        ws.append(["Symbol", "Date", "Qty", "Price", "Tax Deduction"])
        for h in self.eoy_holdings.stocks:
            ws.append([h.symbol, h.date, round(h.qty, 4), round(h.purchase_price.nok_value, 2), round(h.tax_deduction, 2)])
        adjust_width(ws)

        # Save the Excel workbook to a binary blob
        excel_data = BytesIO()
        workbook.save(excel_data)
        excel_data.seek(0)
        return excel_data.getvalue()
