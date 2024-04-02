"""
ESPP portfolio class
"""

import logging
from io import BytesIO
from copy import deepcopy
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field
from datetime import date, datetime
from decimal import Decimal
from espp2.datamodels import (
    Stock,
    Holdings,
    Amount,
    Wires,
    Transactions,
    Dividend_Reinv,
    EOYBalanceItem,
    TaxSummary,
    ForeignShares,
    EOYDividend,
    EOYSales
)
from espp2.fmv import FMV, get_tax_deduction_rate, Fundamentals
from espp2.cash import Cash
from espp2.positions import Ledger
from typing import Any, Dict
from espp2.report import print_cash_ledger
from espp2.console import console

fmv = FMV()
logger = logging.getLogger(__name__)


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
    split: bool = False

    def get_coord(self, key):
        return self.coord[key]

    def qty_at_date(self, exdate):
        """Return qty at date"""
        if self.date > exdate:
            return 0
        qty = self.qty
        for r in self.records:
            if isinstance(r, PortfolioSale) and r.saledate < exdate:
                qty -= abs(r.qty)
        return qty

    def format(self, row, columns):
        """Return a list of cells for a row"""
        col = [(row, columns.index("Symbol"), self.symbol)]
        if not self.split:
            col.append((row, columns.index("Date"), self.date))
        col.append((row, columns.index("Qty"), self.qty))
        col.append(
            (
                row,
                columns.index("Price"),
                f'={index_to_cell(row, columns.index("Price USD"))}*{index_to_cell(row, columns.index("Exchange Rate"))}',
            )
        )
        self.coord["Price"] = index_to_cell(row, columns.index("Price"))
        self.coord["Price USD"] = index_to_cell(row, columns.index("Price USD"))
        col.append((row, columns.index("Price USD"), round(self.purchase_price.value, 2)))
        col.append(
            (row, columns.index("Exchange Rate"), self.purchase_price.nok_exchange_rate)
        )
        col.append((row, columns.index("Tax Ded Acc"), round(self.tax_deduction_acc, 2)))
        col.append((row, columns.index("Tax Ded Add"), round(self.tax_deduction_new, 2)))
        return col


class PortfolioDividend(BaseModel):
    """Stock dividends"""

    divdate: date
    qty: Decimal
    dividend_dps: Amount
    dividend: Amount
    tax_deduction_used: Decimal = 0
    tax_deduction_used_total: Decimal = 0
    parent: PortfolioPosition = None

    def format(self, row, columns):
        """Return a list of cells for a row"""
        col = [(row, columns.index("Date"), self.divdate)]
        col.append((row, columns.index("Type"), "Dividend"))
        col.append((row, columns.index("iQty"), self.qty))
        col.append(
            (row, columns.index("Exchange Rate"), self.dividend_dps.nok_exchange_rate)
        )
        col.append(
            (
                row,
                columns.index("Div PS"),
                f'={index_to_cell(row, columns.index("Div PS USD"))}*{index_to_cell(row, columns.index("Exchange Rate"))}',
            )
        )
        col.append((row, columns.index("Div PS USD"), round(self.dividend_dps.value, 2)))
        col.append(
            (
                row,
                columns.index("Total Dividend"),
                f'={index_to_cell(row, columns.index("Div PS"))}*{index_to_cell(row, columns.index("iQty"))}',
            )
        )

        col.append(
            (
                row,
                columns.index("Total Dividend USD"),
                f'={index_to_cell(row, columns.index("Div PS USD"))}*{index_to_cell(row, columns.index("iQty"))}',
            )
        )
        col.append(
            (row, columns.index("Tax Ded Used"), round(self.tax_deduction_used, 2))
        )
        col.append(
            (
                row,
                columns.index("Tax Ded Total"),
                round(self.tax_deduction_used_total, 2),
            )
        )
        return col


class PortfolioSale(BaseModel):
    # TODO: Fee
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
        col = [(row, columns.index("Date"), self.saledate)]
        col.append((row, columns.index("Type"), "Sale"))
        col.append((row, columns.index("Qty"), self.qty))
        col.append(
            (
                row,
                columns.index("Price"),
                f'={index_to_cell(row, columns.index("Price USD"))}*{index_to_cell(row, columns.index("Exchange Rate"))}',
            )
        )
        col.append((row, columns.index("Price USD"), round(self.sell_price.value, 2)))
        col.append(
            (row, columns.index("Exchange Rate"), self.sell_price.nok_exchange_rate)
        )
        col.append(
            (
                row,
                columns.index("Gain PS"),
                f'={index_to_cell(row, columns.index("Price"))}-{self.parent.get_coord("Price")}',
            )
        )

        col.append(
            (
                row,
                columns.index("Gain PS USD"),
                f'={index_to_cell(row, columns.index("Price USD"))}-{self.parent.get_coord("Price USD")}',
            )
        )

        col.append(
            (
                row,
                columns.index("Gain"),
                f'={index_to_cell(row, columns.index("Gain PS"))}*ABS({index_to_cell(row, columns.index("Qty"))})',
            )
        )
        col.append(
            (
                row,
                columns.index("Gain USD"),
                f'={index_to_cell(row, columns.index("Gain PS USD"))}*ABS({index_to_cell(row, columns.index("Qty"))})',
            )
        )
        col.append(
            (
                row,
                columns.index("Amount"),
                f'=ABS({index_to_cell(row, columns.index("Price"))}*{index_to_cell(row, columns.index("Qty"))})',
            )
        )
        col.append(
            (
                row,
                columns.index("Amount USD"),
                f'=ABS({index_to_cell(row, columns.index("Price USD"))}*{index_to_cell(row, columns.index("Qty"))})',
            )
        )
        col.append(
            (row, columns.index("Tax Ded Used"), round(self.tax_deduction_used, 2))
        )
        col.append(
            (
                row,
                columns.index("Tax Ded Total"),
                round(self.tax_deduction_used_total, 2),
            )
        )
        return col


def adjust_width(ws):
    def as_text(value):
        if value is None:
            return ""
        return str(value)

    # Adjust column width to fit the longest value in each column
    for column_cells in ws.columns:
        length = max(len(as_text(cell.value)) for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = length + 1


def index_to_cell(row, column):
    """
    Convert a row and column index to an Excel cell reference.
    """
    column_letter = get_column_letter(column + 1)
    return f"{column_letter}{row}"


class Portfolio:
    def buy(self, p):
        position = PortfolioPosition(
                qty=p.qty,
                purchase_price=p.purchase_price,
                date=p.date,
                symbol=p.symbol,
                tax_deduction_acc=0,
                current_qty=p.qty,
            )
        self.positions.append(position)

        # Keep stock of new positions for reporting
        self.new_positions.append(position)

    def dividend(self, transaction):
        """Dividend"""
        shares_left = transaction.amount.value / transaction.dividend_dps
        total = transaction.amount.value
        # Walk through positions available at exdate.
        for p in self.positions:
            if p.symbol == transaction.symbol:
                # Get qty up until exdate
                qty = p.qty_at_date(transaction.exdate)
                if qty == 0:
                    continue
                assert (
                    p.date <= transaction.exdate
                ), f"Exdate {transaction.exdate} before purchase date {p.date} shares left {shares_left}"
                if qty >= shares_left:
                    shares_left = 0
                else:
                    shares_left -= qty

                used = transaction.dividend_dps * qty
                # used_nok = used * transaction.amount.nok_exchange_rate
                total -= used
                d = PortfolioDividend(
                    divdate=transaction.date,
                    qty=qty,
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
                    parent=p,
                )
                p.records.append(d)
                if shares_left == 0:
                    break
        if abs(total) > 1:
            logger.error(f"Not all dividend used: {total}")
        self.cash.debit(transaction.date, transaction.amount, "dividend")

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
        self.cash.credit(transaction.date, transaction.amount, "tax")

    def tax_for_symbol(self, symbol):
        total_nok = 0
        total_usd = 0
        for t in self.taxes:
            if t["symbol"] == symbol:
                total_nok += t["amount"].nok_value
                total_usd += t["amount"].value
        return total_usd, total_nok

    def dividend_reinv(self, transaction: Dividend_Reinv):
        self.cash.credit(transaction.date, transaction.amount, "dividend reinvest")

    def sell(self, transaction):
        shares_to_sell = abs(transaction.qty)

        # This is the net amount after fees
        actual = transaction.amount.value
        # if transaction.fee is not None:
        #     actual -= abs(transaction.fee.value)
        sell_price = Amount(
            amountdate=transaction.date,
            value=(actual / shares_to_sell),
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
                    parent=p,
                )
                p.records.append(s)
                if shares_to_sell == 0:
                    break
        self.cash.debit(transaction.date, transaction.amount.model_copy(), "sale")
        # Sale is reported as net value after fees.
        # if transaction.fee is not None:
        #     self.cash.credit(transaction.date, transaction.fee.model_copy(), "sale fee")

    def sell_split(self, transaction, poscopy):
        '''If a sale is split over multiple records, split the position'''
        shares_to_sell = abs(transaction.qty)
        for i, p in enumerate(poscopy):
            if p.symbol != transaction.symbol or p.current_qty == 0:
                continue
            if p.current_qty == shares_to_sell:
                p.current_qty = 0
                shares_to_sell = 0
            elif p.current_qty > shares_to_sell:
                # Split record
                splitpos = deepcopy(p)
                splitpos.current_qty = p.current_qty - shares_to_sell
                splitpos.qty = splitpos.current_qty
                splitpos.split = True
                p.current_qty -= shares_to_sell
                self.positions[i].qty = self.positions[i].current_qty = shares_to_sell
                self.positions.insert(i+1, splitpos)
                logger.debug(f"Splitting position: {p.symbol} {p.date}, {shares_to_sell}+{splitpos.qty}({p.qty})")

                shares_to_sell = 0
            else:
                shares_to_sell -= p.current_qty
                p.current_qty = 0
            if shares_to_sell == 0:
                break


    def buys(self):
        """Return report of BUYS"""
        r = []
        for symbol in self.symbols:
            bought = 0
            price_sum = 0
            price_sum_nok = 0
            no_pos = 0
            for item in self.new_positions:
                if item.symbol != symbol:
                    continue
                bought += item.qty
                price_sum += item.purchase_price.value
                price_sum_nok += item.purchase_price.nok_value
                no_pos += 1
            if no_pos > 0:
                avg_usd = price_sum / no_pos
                avg_nok = price_sum_nok / no_pos
                r.append(
                    {
                        "symbol": symbol,
                        "qty": bought,
                        "avg_usd": avg_usd,
                        "avg_nok": avg_nok,
                    }
                )
        return r


    def sales(self):
        sales_report = {}
        for p in self.positions:
            for r in p.records:
                if isinstance(r, PortfolioSale):
                    s_record = EOYSales(
                    date=r.saledate,
                    symbol=p.symbol,
                    qty=r.qty,
                    # fee=r.fee,
                    amount=r.total,
                    from_positions=[],
                    )

                    totals = {
                    "gain": r.gain,
                    "purchase_price": p.purchase_price,
                    "tax_ded_used": r.tax_deduction_used * abs(r.qty),
                    }
                    s_record.totals = totals
                    if p.symbol not in sales_report:
                        sales_report[p.symbol] = []
                    sales_report[p.symbol].append(s_record)
        return sales_report
    def fees(self):
        return []


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
        self.cash.debit(transaction.date, transaction.amount, "tax returned")

        self.taxes.append(
            {
                "date": transaction.date,
                "symbol": transaction.symbol,
                "amount": transaction.amount,
            }
        )


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

    '''
    def generate_tax_summary(self):
        # Generate foreign shares for tax report
        foreignshares = []
        credit_deduction = []
        # cashsummary = CashSummary()
        end_of_year = f"{self.year}-12-31"
        eoy_exchange_rate = fmv.get_currency("USD", end_of_year)

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
            foreignshares.append(
                ForeignShares(
                    symbol=s,
                    isin=f.isin,
                    country=f.country,
                    account=self.broker,
                    shares=total_qty,
                    wealth=wealth_nok,
                    dividend=dividend_nok,
                    taxable_gain=taxable_gain,
                    tax_deduction_used=tax_deduction_used,
                )
            )
        return TaxSummary(
            year=self.year,
            foreignshares=foreignshares,
            credit_deduction=credit_deduction,
            cashsummary=self.cash_report,
        )
        '''

    def eoy_balance(self, year):
        """End of year summary of holdings"""
        assert (
            year == self.year or year == self.year - 1
        ), f"Year {year} does not match portfolio year {self.year}"
        end_of_year = f"{year}-12-31"

        eoy_exchange_rate = fmv.get_currency("USD", end_of_year)
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
            r.append(
                EOYBalanceItem(
                    symbol=symbol,
                    qty=total_shares,
                    amount=Amount(
                        value=total_shares * eoyfmv,
                        currency="USD",
                        nok_exchange_rate=eoy_exchange_rate,
                        nok_value=total_shares * eoyfmv * eoy_exchange_rate,
                    ),
                    fmv=eoyfmv,
                )
            )
        return r

    def generate_holdings(self, year, broker):
        # Generate holdings for EOY.
        holdings = []
        assert year == self.year, f"Year {year} does not match portfolio year {self.year}"
        for p in self.positions:
            if p.current_qty == 0:
                continue
            hitem = Stock(
                date=p.date,
                symbol=p.symbol,
                qty=p.current_qty,
                purchase_price=p.purchase_price,
                tax_deduction=p.tax_deduction,
            )
            holdings.append(hitem)
        #
        # TODO: FIX CASH
        #
        return Holdings(year=self.year, broker=self.broker, stocks=holdings, cash=[])

    def holdings(self, year, broker):
        return self.generate_holdings(year, broker)

    def fundamentals(self) -> Dict[str, Fundamentals]:
        """Return fundamentals for symbol at date"""
        r = {}
        for symbol in self.symbols:
            fundamentals = fmv.get_fundamentals(symbol)
            isin = fundamentals.get("General", {}).get("ISIN", None)
            if not isin:
                isin = fundamentals.get("ETF_Data", {}).get("ISIN", "")

            r[symbol] = Fundamentals(
                name=fundamentals["General"]["Name"],
                isin=isin,
                country=fundamentals["General"]["CountryName"],
                symbol=fundamentals["General"]["Code"],
            )
        return r

    def dividends(self):
        result = []
        for s in self.symbols:
            # For loop for all self.positions where p.symbol == s
            usd = 0
            nok = 0
            tax_ded_used = 0

            tax_usd, tax_nok = self.tax_for_symbol(s)
            for p in self.positions:
                if p.symbol != s:
                    continue
                for r in p.records:
                    if isinstance(r, PortfolioDividend):
                        usd += r.dividend.value
                        nok += r.dividend.nok_value
                        tax_ded_used += r.tax_deduction_used_total


            result.append(EOYDividend(
                symbol=s,
                amount=Amount(
                    currency="USD",
                    value=usd,
                    nok_value=nok - tax_ded_used,
                    nok_exchange_rate=0,
                ),
                gross_amount=Amount(
                    currency="USD",
                    value=usd,
                    nok_value=nok,
                    nok_exchange_rate=0,
                ),
                tax=Amount(
                    currency="USD",
                    value=tax_usd,
                    nok_value=tax_nok,
                    nok_exchange_rate=0,
                ),
                tax_deduction_used=tax_ded_used,
            ))
        return result

    def __init__(  # noqa: C901
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
        self.new_positions = []
        self.cash = Cash(year=year, opening_balance=holdings.cash)
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

        #######################
        # Pre-Process buy/sell transactions, split positions as required
        for t in transactions:
            if t.type in ["BUY", "DEPOSIT"]:
                self.buy(t)
        poscopy = deepcopy(self.positions)
        for t in transactions:
            if t.type in ["SELL"]:
                self.sell_split(t, poscopy)
        #######################

        for t in transactions:
            # Use dispatch to call a function per t.type
            if t.type in ["BUY", "DEPOSIT"]:    # Already handled these
                continue
            self.__class__.dispatch[t.type](self, t)

        # Add tax deduction to the positions held by the end of the year
        total_tax_deduction = 0

        # Find the set of different symbolds in self.positions
        self.symbols = {p.symbol for p in self.positions}
        for p in self.positions:
            if p.current_qty > 0:
                tax_deduction_rate = get_tax_deduction_rate(self.year)
                tax_deduction = (
                    (p.purchase_price.nok_value + p.tax_deduction) * tax_deduction_rate
                ) / 100
                p.tax_deduction_new = tax_deduction
                logger.debug(
                    "Position that gets tax deduction for this year: "
                    f"{p.symbol} {p.date} {p.current_qty} {p.tax_deduction_new}"
                )
            p.tax_deduction = p.tax_deduction_acc + p.tax_deduction_new
            total_tax_deduction += p.tax_deduction * p.qty

        logger.debug(f"Total tax deduction {total_tax_deduction}")

        # Walk through and use the available tax deduction
        # Use tax deduction for dividend if we can. Then for sales. Then keep leftovers for next year.
        for p in self.positions:
            if p.tax_deduction > 0:
                # Walk through records looking for dividends
                for r in p.records:
                    # The qty we get dividends for is different from the qty we get tax dividends for
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
        db_wires = [t for t in transactions if t.type == "WIRE"]
        unmatched = self.cash.wire(db_wires, wires)
        self.unmatched_wires = unmatched
        self.unmatched_wires_report = unmatched
        cash_report = self.cash.process()
        self.cash_report = cash_report
        self.cash_summary = cash_report
        # print("CASH REPORT", cash_report)
        self.cash_ledger = self.cash.ledger()
        # print_cash_ledger(self.ledger, console)
        self.ledger = Ledger(holdings, transactions)

        # Generate holdings for next year.
        self.eoy_holdings = self.generate_holdings(year, broker)
        # self.summary = self.generate_tax_summary()

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
        for stock in portfolio:
            for row, col, value in stock.format(row, self.column_headers):
                ws.cell(row=row, column=col + 1, value=value)
            row += 1
            for record in stock.records:
                for row, col, value in record.format(row, self.column_headers):
                    ws.cell(row=row, column=col + 1, value=value)
                row += 1

        # Set number format for the entire column
        sum_cols = ["D", "M", "N", "O", "P", "S", "T", "V"]
        no_columns = len(ws[sum_cols[0]])
        ws[f"A{no_columns+1}"] = "Total"
        for col in sum_cols:
            ws[f"{col}{no_columns+1}"] = f"=SUM({col}2:{col}{no_columns})"
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
        c = ws["A2"]
        ws.freeze_panes = c

        # Separate sheet for cash
        ws = workbook.create_sheet("Cash")
        ws.append(["Date", "Description", "Amount", "Amount USD", "Total"])
        for c in self.cash_ledger:
            ws.append(
                [
                    c[0].date,
                    c[0].description,
                    round(c[0].amount.nok_value, 2),
                    round(c[0].amount.value, 2),
                    round(c[1], 2),
                ]
            )

        adjust_width(ws)

        # Separate sheet for EOY holdings
        ws = workbook.create_sheet("EOY Holdings")
        ws.append(["Symbol", "Date", "Qty", "Price", "Tax Deduction"])
        for h in self.eoy_holdings.stocks:
            ws.append(
                [
                    h.symbol,
                    h.date,
                    round(h.qty, 4),
                    round(h.purchase_price.nok_value, 2),
                    round(h.tax_deduction, 2),
                ]
            )
        adjust_width(ws)

        # Save the Excel workbook to a binary blob
        excel_data = BytesIO()
        workbook.save(excel_data)
        excel_data.seek(0)
        return excel_data.getvalue()
