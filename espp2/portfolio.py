from copy import deepcopy
from openpyxl import Workbook
from openpyxl.formatting import Rule
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.styles import Font
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
)
from espp2.fmv import get_tax_deduction_rate
from espp2.cash import Cash
from typing import Any, ClassVar
from espp2.report import print_cash_ledger
from espp2.console import console


def format_cells(ws, column, number_format):
    for cell in ws[column]:
        cell.number_format = number_format


def insert_in_list(columns, l, col, value):
    i = columns.index(col)
    l[i] = value


# from rich import print
class PortfolioDividend(BaseModel):
    """Stock dividends"""

    divdate: date
    qty: Decimal = Field(decimal_places=4)
    dividend_dps: Amount
    dividend: Amount
    tax_deduction_used: Decimal = 0
    tax_deduction_used_total: Decimal = 0

    def format(self, columns):
        l = [""] * len(columns)
        insert_in_list(columns, l, "Date", self.divdate)
        insert_in_list(columns, l, "Type", "Dividend")
        insert_in_list(columns, l, "iQty", self.qty)
        insert_in_list(columns, l, "Exchange Rate", self.dividend_dps.nok_exchange_rate)
        insert_in_list(columns, l, "Div PS USD", round(self.dividend_dps.value, 2))
        insert_in_list(columns, l, "Div", round(self.dividend.nok_value, 2))
        insert_in_list(columns, l, "Div USD", round(self.dividend.value, 2))
        insert_in_list(columns, l, "Tax Ded Used", round(self.tax_deduction_used, 2))
        insert_in_list(
            columns, l, "Tax Ded Total", round(self.tax_deduction_used_total, 2)
        )
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

    def format(self, columns):
        l = [""] * len(columns)
        insert_in_list(columns, l, "Date", self.saledate)
        insert_in_list(columns, l, "Type", "Sale")
        insert_in_list(columns, l, "Qty", self.qty)
        insert_in_list(columns, l, "Price", round(self.sell_price.nok_value, 2))
        insert_in_list(columns, l, "Price USD", round(self.sell_price.value, 2))
        insert_in_list(columns, l, "Exchange Rate", self.sell_price.nok_exchange_rate)
        insert_in_list(columns, l, "Gain PS", round(self.gain_ps.nok_value, 2))
        insert_in_list(columns, l, "Gain PS USD", round(self.gain_ps.value, 2))
        insert_in_list(columns, l, "Gain", round(self.gain.nok_value, 2))
        insert_in_list(columns, l, "Gain USD", round(self.gain.value, 2))
        insert_in_list(columns, l, "Amount", round(self.total.nok_value, 2))
        insert_in_list(columns, l, "Amount USD", round(self.total.value, 2))
        insert_in_list(columns, l, "Tax Ded Used", round(self.tax_deduction_used, 2))
        insert_in_list(
            columns, l, "Tax Ded Total", round(self.tax_deduction_used_total, 2)
        )
        return l


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

        self.column_headers = [
            "Symbol",
            "Date",
            "Type",
            "Qty",
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
            "Div PS USD",
            "Div",
            "Div USD",
            "iQty",
            "Tax Ded Used",
            "Tax Ded Total",
        ]

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

        for t in transactions:
            # Use dispatch to call a function per t.type
            self.__class__.dispatch[t.type](self, t)

        # Add tax deduction to the positions held by the end of the year
        for p in self.positions:
            if p.current_qty > 0:
                tax_deduction_rate = get_tax_deduction_rate(self.year)
                tax_deduction = (
                    (p.purchase_price.nok_value + p.tax_deduction) * tax_deduction_rate
                ) / 100
                p.tax_deduction_new = tax_deduction
            p.tax_deduction = p.tax_deduction_acc + p.tax_deduction_new

        # Walk through and use the available tax deduction
        # Use tax deduction for dividend if we can. Then for sales. Then keep for next year.
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
                        if p.tax_deduction >= r.gain_ps.nok_value:
                            p.tax_deduction -= r.gain_ps.nok_value
                            r.tax_deduction_used = r.gain_ps.nok_value
                            r.tax_deduction_used_total = r.gain_ps.nok_value * r.qty
                        else:
                            r.tax_deduction_used = p.tax_deduction
                            r.tax_deduction_used_total = p.tax_deduction * r.qty
                            p.tax_deduction = 0

        # Process wires
        db_wires = [t for t in transactions if t.type == 'WIRE']
        unmatched = self.cash.wire(db_wires, wires)
        print("Unmatched wires", unmatched)
        cash_report = self.cash.process()
        print('CASH REPORT', cash_report)
        self.ledger = self.cash.ledger()
        print_cash_ledger(self.ledger, console)

        self.excel_report()

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
        for stock in portfolio:
            ws.append(
                [
                    stock.symbol,
                    stock.date,
                    "",
                    round(stock.qty, 4),
                    round(stock.purchase_price.nok_value, 2),
                    round(stock.purchase_price.value, 2),
                    round(stock.purchase_price.nok_exchange_rate, 6),
                    round(stock.tax_deduction_acc, 2),
                    round(stock.tax_deduction_new, 2),
                ]
            )
            for record in stock.records:
                ws.append(record.format(self.column_headers))

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
                    t["date"],
                    t["symbol"],
                    round(t["amount"].nok_value, 2),
                    round(t["amount"].value, 2),
                ]
            )

        # Specify the Excel file path
        excel_file_path = "stock_data.xlsx"

        def as_text(value):
            if value is None:
                return ""
            return str(value)

        # Adjust column width to fit the longest value in each column
        for column_cells in ws.columns:
            length = max(len(as_text(cell.value)) for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = length + 1

        # Freeze the first row
        c = ws['A2']
        ws.freeze_panes = c

        # Separate sheet for cash
        ws = workbook.create_sheet("Cash")
        ws.append(["Date", "Description", "Amount", "Amount USD", "Total"])
        for c in self.ledger:
            ws.append([c[0].date, c[0].description, round(c[0].amount.nok_value, 2),
                       round(c[0].amount.value, 2), round(c[1], 2)])

        # Save the Excel workbook to a file
        workbook.save(excel_file_path)

        print(f"Data written to {excel_file_path}")
