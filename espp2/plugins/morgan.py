"""
Morgan Stanley HTML table transaction history normalizer.
"""

# pylint: disable=invalid-name
# pylint: disable=no-name-in-module
# pylint: disable=no-self-argument

import math
from decimal import Decimal
import html5lib
from pydantic import TypeAdapter
from espp2.fmv import FMV
from espp2.datamodels import (
    Transactions,
    Entry,
    EntryTypeEnum,
    Amount,
    NegativeAmount,
    TransactionTaxYearBalances,
)
import re
import logging
import datetime
from pandas import MultiIndex, Index

logger = logging.getLogger(__name__)
currency_converter = FMV()


def setitem(rec, name, val):
    """Used to set cell-values from a table by to_dict() function"""
    if val is None:
        return
    if isinstance(val, float):
        if math.isnan(val):
            return
        rec[name] = Decimal(f"{val}")
        return
    if not isinstance(val, str):
        raise ValueError(f"setitem() expected string, got {val}")
    rec[name] = val


def close_to_zero(value, strval):
    if value >= Decimal(f"-{strval}") and value <= Decimal(strval):
        return True
    return False


class Table:
    def __init__(self, tablenode, idx):
        self.tablenode = tablenode
        self.data = decode_data(tablenode)
        self.colnames = []
        self.colname2idx = dict()
        self.header = []
        self.rows = []
        self.idx = idx

    def get(self, row, colname):
        try:
            idx = self.colname2idx[colname]
        except KeyError:
            return None
        if idx >= len(row):
            return None
        return row[idx]

    def to_dict(self):
        rc = []
        for row in self.rows:
            rec = dict()
            for colname in self.colname2idx.keys():
                setitem(rec, colname, self.get(row, colname))
            rc.append(rec)
        return rc


class ParseState:
    def __init__(self, filename):
        self.source = f"morgan:{filename}"
        self.transactions = []
        self.activity = "<unknown>"
        self.symbol = None
        self.entry_date = None
        self.date2dividend = dict()
        self.adapter = TypeAdapter(Entry)
        self.settledate2saleswithdrawals = dict()
        self.espp_purchase_date2price = dict()

        self.opening_value_cash = Decimal(0)
        self.opening_value_shares = Decimal(0)
        self.closing_value_cash = Decimal(0)
        self.closing_value_shares = Decimal(0)

    def parse_activity(self, row):
        """Parse the "Activity" column"""
        self.activity = getitem(row, "Activity")

    def parse_entry_date(self, row):
        """Parse the "Entry Date" date, common to many tables"""
        date = getitem(row, "Entry Date")
        if date is None:
            raise ValueError(f"Entry-date is not provided for {row}")
        self.entry_date = fixup_date(date)

    def parse_fund_symbol(self, row, column):
        """Parse the "Fund: CSCO - NASDAQ" type headers"""
        item, ok = getitems(row, column)
        if ok:
            m = re.match(r"""^Fund:\s+([A-Za-z]+)\s""", item)
            if m:
                self.symbol = m.group(1)
                if self.symbol == "Cash":
                    self.symbol = None
                else:
                    # Too many unknowns to support other shares than Cisco
                    assert self.symbol == "CSCO"
                return True  # No more parsing needed
        return False

    def deposit(self, qty, purchase_price, description, purchase_date=None):
        assert self.symbol is not None

        r = {
            "type": EntryTypeEnum.DEPOSIT,
            "date": self.entry_date,
            "qty": qty,
            "symbol": self.symbol,
            "description": description,
            "purchase_price": purchase_price,
            "purchase_date": purchase_date,
            "source": self.source,
            "broker": "morgan",
        }

        if description == "ESPP" and purchase_date in self.espp_purchase_date2price:
            r["discounted_purchase_price"] = self.espp_purchase_date2price[
                purchase_date
            ]

        self.transactions.append(self.adapter.validate_python(r))

    def sell(self, qty, price):
        assert self.symbol is not None

        gross = self.get_gross_sales_price(-qty, price, self.entry_date)

        r = {
            "type": EntryTypeEnum.SELL,
            "date": self.entry_date,
            "qty": qty,
            "amount": fixup_price(self.entry_date, "USD", f"{gross}"),
            "symbol": self.symbol,
            "description": self.activity,
            "source": self.source,
        }

        self.transactions.append(self.adapter.validate_python(r))

    def dividend(self, amount):
        assert self.symbol is not None

        date = self.entry_date

        r = {
            "type": EntryTypeEnum.DIVIDEND,
            "date": date,
            "symbol": self.symbol,
            "amount": amount,
            "source": self.source,
            "description": "Credit",
        }

        if date in self.date2dividend:
            rr = self.date2dividend[date]
            # assert r["amount"]["nok_exchange_rate"] == rr.amount.nok_exchange_rate
            rr.amount.value += r["amount"]["value"]
            # rr.amount.nok_value += r["amount"]["nok_value"]
            # print(f"### DIV: {date} +{r['amount']['value']} (Again)")
            return

        # print(f"### DIV: {date} +{r['amount']['value']} (First)")
        self.date2dividend[date] = self.adapter.validate_python(r)

    def flush_dividend(self):
        for date in self.date2dividend.keys():
            self.transactions.append(self.date2dividend[date])

    def dividend_reinvest(self, amount):
        assert self.symbol is not None

        r = {
            "type": EntryTypeEnum.DIVIDEND_REINV,
            "date": self.entry_date,
            "symbol": self.symbol,
            "amount": amount,
            "source": self.source,
            "description": "Debit",
        }

        self.transactions.append(self.adapter.validate_python(r))

    def wire_transfer(self, date, amount, fee):
        r = {
            "type": EntryTypeEnum.WIRE,
            "date": date,
            "amount": amount,
            "description": "Cash Disbursement",
            "fee": fee,
            "source": self.source,
        }

        self.transactions.append(self.adapter.validate_python(r))

    def cashadjust(self, date, amount, description):
        """Ad-hoc cash-adjustment (positive or negative)"""
        r = {
            "type": EntryTypeEnum.CASHADJUST,
            "date": date,
            "amount": amount,
            "description": description,
            "source": self.source,
        }

        self.transactions.append(self.adapter.validate_python(r))

    def taxreversal(self, amount):
        # This is a hack - Tax reversal seems not tied to a particular share
        symbol = "CSCO" if self.symbol is None else self.symbol

        r = {
            "type": EntryTypeEnum.TAXSUB,
            "date": self.entry_date,
            "amount": amount,
            "symbol": symbol,
            "description": self.activity,
            "source": self.source,
        }

        self.transactions.append(self.adapter.validate_python(r))
        return True

    def record_sales_withdrawal(self, withdrawal):
        """Record a Withdrawal record for a sales operation"""
        settle_date = withdrawal.settlement_date
        if settle_date not in self.settledate2saleswithdrawals:
            self.settledate2saleswithdrawals[settle_date] = []
        self.settledate2saleswithdrawals[settle_date].append(withdrawal)

    def get_gross_sales_price(self, qty, price, salesdate):
        """Compute qty * price, but use Withdrawal gross for date if suitable"""
        gross_calc = qty * price
        try:
            for w in self.settledate2saleswithdrawals[salesdate]:
                assert w.gross_amount.currency == "USD"
                gross_given = w.gross_amount.value
                grossprice = gross_given / qty
                diff = grossprice - price
                # print(f"### get_gross_sales_price({salesdate}) {gross_calc} => {gross_given} ?  diff={diff}")
                if diff >= Decimal("-0.01") and diff <= Decimal("0.01"):
                    if gross_calc != gross_given:
                        print(
                            f"### Sale at {salesdate}: Using gross {gross_given} for qty={qty} price={price} ({gross_calc})"
                        )
                    return gross_given
        except KeyError:
            pass
        return gross_calc

    def fixup_selldates(self):
        """Change SELL-records to use actual selldate"""
        # TODO!!!! Fixing now needs to patch amountdate in the Amount instance for sales!
        # TODO!!!! This is *not* needed for latest test-files; maybe more complicated
        # than first anticipated. Disabled for now.
        # TODO!!!! If this is revived, it needs to use settledate2saleswithdrawals
        for t in self.transactions:
            if t.type == EntryTypeEnum.SELL:
                settledate = t.date.isoformat()
                if settledate in self.settledate2selldate:
                    selldate = self.settledate2selldate[settledate]
                    t.date = datetime.date.fromisoformat(selldate)
                    logger.warning(
                        f"Sale on {settledate} assumed to have happened on {t.date} (Withdrawal-date)"
                    )

    def parse_opening_value(self, row):
        """Record opening value for cash and shares"""
        if self.activity != "Opening Value":
            return False
        cash, cash_ok = getitems(row, "Cash")
        qty, qty_ok = getitems(row, "Number of Shares")

        if cash_ok:
            cashval, currency = morgan_price(cash)
            assert currency == "USD"
            self.opening_value_cash += cashval
            print(f">>> Opening value: ${cashval}")

        if qty_ok:
            qty = morgan_qty(qty)
            self.opening_value_shares += qty
            print(f">>> Opening value: qty={qty}")

        return True

    def parse_closing_value(self, row):
        """Record closing value for cash and shares"""
        if self.activity != "Closing Value":
            return False
        cash, cash_ok = getitems(row, "Cash")
        qty, qty_ok = getitems(row, "Number of Shares")

        if cash_ok:
            cashval, currency = morgan_price(cash)
            assert currency == "USD"
            self.closing_value_cash += cashval
            print(f">>> Closing value: ${cashval}")

        if qty_ok:
            qty = morgan_qty(qty)
            self.closing_value_shares += qty
            print(f">>> Closing value: qty={qty}")

        return True

    def parse_rsu_release(self, row):
        """Handle what appears to be RSUs added to account"""
        m = re.match(r"""^Release\s+\(([A-Z0-9]+)\)""", self.activity)
        if not m:
            return False

        id = m.group(1)  # noqa: F841 # Unused for now
        qty, value, ok = getitems(row, "Number of Shares", "Book Value")
        if not ok:
            raise ValueError(f"Missing columns for {row}")
        qty = Decimal(qty)
        book_value, currency = morgan_price(value)
        purchase_price = fixup_price2(self.entry_date, currency, book_value / qty)

        self.deposit(qty, purchase_price, "RS", self.entry_date)
        return True

    def parse_dividend_reinvest(self, row):
        """Reinvestment of dividend through bying same share"""
        if self.activity != "You bought (dividend)":
            return False

        qty, price, ok = getitems(row, "Number of Shares", "Share Price")
        if not ok:
            raise ValueError(f"Missing columns for {row}")

        qty = Decimal(qty)
        price, currency = morgan_price(price)

        amount = fixup_price(self.entry_date, currency, f"{price * -qty}")
        self.dividend_reinvest(amount)

        purchase_price = fixup_price2(self.entry_date, currency, price)
        self.deposit(qty, purchase_price, "Dividend re-invest", self.entry_date)
        return True

    def parse_sale(self, row):
        if self.activity != "Sale":
            return False
        qty, price, ok = getitems(row, "Number of Shares", "Share Price")
        if not ok:
            raise ValueError(f"Missing colummns for {row}")
        price, currency = morgan_price(price)
        qty = Decimal(qty)
        price = Decimal(price)

        self.sell(qty, price)
        return True

    def parse_deposit(self, row):
        if self.activity != "Share Deposit" and self.activity != "Historical Purchase":
            return False
        qty, ok = getitems(row, "Number of Shares")
        if not ok:
            raise ValueError(f"Missing columns for {row}")
        qty = Decimal(qty)
        price = currency_converter[(self.symbol, self.entry_date)]
        purchase_price = fixup_price2(self.entry_date, "ESPPUSD", price)

        self.deposit(qty, purchase_price, "ESPP", self.entry_date)
        return True

    def parse_dividend_cash(self, row):
        """This, despite its logged description, results in shares-reinvest"""
        if self.activity != "Dividend (Cash)":
            return False
        qty, qty_ok = getitems(row, "Number of Shares")
        cash, cash_ok = getitems(row, "Cash")

        if qty_ok and cash_ok:
            raise ValueError(f"Unexpected cash+shares for dividend: {row}")

        if qty_ok:
            qty = Decimal(qty)
            price = currency_converter[(self.symbol, self.entry_date)]
            purchase_price = fixup_price2(self.entry_date, "USD", price)
            self.deposit(
                qty, purchase_price, "Dividend re-invest (Cash)", self.entry_date
            )

            amount = fixup_price(self.entry_date, "USD", f"{price * -qty}")
            self.dividend_reinvest(amount)

        if cash_ok:
            amount = fixup_price(self.entry_date, "USD", cash)
            self.dividend(amount)

        return True

    def parse_tax_withholding(self, row):
        """Record taxes withheld"""
        if (
            self.activity != "Withholding"
            and self.activity != "IRS Nonresident Alien Withholding"
            and self.activity != "IRS Backup Withholding"
        ):
            return False
        taxed, ok = getitems(row, "Cash")
        if not ok:
            raise ValueError(f"Expected Cash data for tax record: {row}")

        # print(f'parse_tax_withholding: date={self.entry_date} activity={self.activity} taxed={taxed}')
        amount = fixup_price(self.entry_date, "USD", taxed)
        symbol = "CSCO" if self.symbol is None else self.symbol

        r = {
            "type": EntryTypeEnum.TAX,
            "date": self.entry_date,
            "amount": amount,
            "symbol": symbol,
            "description": self.activity,
            "source": self.source,
        }

        self.transactions.append(self.adapter.validate_python(r))

        return True

    def parse_opening_balance(self, row):
        """Opening balance for shares is used to add historic shares..."""
        if self.activity != "Opening Balance":
            return False
        qty, bookvalue_txt, ok = getitems(row, "Number of Shares", "Book Value")
        if ok:
            qty = Decimal(qty)
            if qty > 0 and False:
                # Disabled for now, check more thoroughly before enabling
                book_value, currency = morgan_price(bookvalue_txt)
                purchase_price = fixup_price2(
                    self.entry_date, currency, book_value / qty
                )
                self.deposit(qty, purchase_price, "RS", self.entry_date)
                return True
        raise ValueError(f"Unexpected opening balance: {row}")

    def parse_tax_returned(self, row):
        """Parse records that returns paid tax to cash-account"""
        if (
            self.activity == "Nonresident Alien Withholding Transfer"
            or self.activity == "Backup Withholding Refund Transfer"
        ):
            # Assume this is getting tax back? Looks like it...
            # Or it should mean the withheld amount wasn't used for tax
            cash, ok = getitems(row, "Cash")
            if not ok:
                raise ValueError("Expected Cash for Tax reversal")
            value, currency = morgan_price(cash)
            amount = fixup_price2(self.entry_date, currency, value)
            self.taxreversal(amount)
            return True
        return False

    def parse_cash_adjustments(self, row):
        """Parse misc cash-balance adjustment records"""
        if self.activity == "Adhoc Adjustment":
            # We have no idea what this is, but it affects chash holdings...
            # But we've also seen it affect number of shares, probably as
            # a fix for a missing or incorrect RSU/ESPP transaction...
            rc = False
            cash, ok = getitems(row, "Cash")
            if ok:
                value, currency = morgan_price(cash)
                amount = fixup_price2(self.entry_date, currency, value)
                self.cashadjust(self.entry_date, amount, "Adhoc Adjustment")
                rc = True
            qty, value, ok = getitems(row, "Number of Shares", "Book Value")
            if ok:
                qty = Decimal(qty)
                if qty > 0:
                    book_value, currency = morgan_price(value)
                    purchase_price = fixup_price2(
                        self.entry_date, currency, book_value / qty
                    )
                    self.deposit(qty, purchase_price, "RS", self.entry_date)
                    logger.warning(
                        f"Adhoc Adjustment adds {qty} shares on {self.entry_date}, assuming these are RSU shares"
                    )
                    rc = True

            if not rc:
                raise Exception("Adhoc adjustment not as expected")
            return rc

        return False


def find_all_tables(document):
    nodes = document.findall(".//{http://www.w3.org/1999/xhtml}table", None)
    rc = []
    for e, n in zip(nodes, range(0, 10000)):
        rc.append(Table(e, n))
    return rc


def create_signed_amount(
    currency,
    value,
    amountdate,
    negative_ok=True,
    positive_ok=True,
    negate=False,
):
    assert positive_ok or negative_ok

    if negate:
        value *= -1

    if value > 0 and positive_ok:
        return Amount(
            currency=currency,
            value=value,
            amountdate=amountdate,
        )

    if value < 0 and negative_ok:
        return NegativeAmount(
            currency=currency,
            value=value,
            amountdate=amountdate,
        )

    if positive_ok:
        if value < 0:
            raise Exception(f"Expected positive number, got {value}")
        return Amount(currency=currency, value=value, amountdate=amountdate)

    if negative_ok:
        if value > 0:
            raise Exception(f"Expected negative number, got {value}")
        return NegativeAmount(currency=currency, value=value, amountdate=amountdate)

    raise Exception("Unexpected, should never get here")


def verify_sign(value, positive_ok, negative_ok):
    if value < 0 and not negative_ok:
        raise Exception("Value {value} must be positive")
    if value > 0 and not positive_ok:
        raise Exception("Value {value} must be negative")


def morgan_price(price_str):
    """Parse price string."""
    # import IPython
    # IPython.embed()
    if " " in price_str:
        value, currency = price_str.split(" ")
    else:
        value, currency = price_str, "USD"

    return Decimal(value.replace("$", "").replace(",", "")), currency


def morgan_qty(qty_str):
    """Parse a quantity entity, with comma as thousands separator"""
    m = re.fullmatch(r"""(\d+),(\d\d\d(\.\d+)?)""", qty_str)
    if m:
        return Decimal(f"{m.group(1)}{m.group(2)}")
    m = re.fullmatch(r"""(\d+(\.\d+)?)""", qty_str)
    if m:
        return Decimal(m.group(1))
    raise ValueError(f"Failed to parse QTY '{qty_str}'")


def fixup_price(datestr, currency, pricestr, change_sign=False):
    """Fixup price."""
    # print('fixup_price:::', datestr, currency, pricestr, change_sign)
    price, currency = morgan_price(pricestr)
    if change_sign:
        price = price * -1
    return {
        "currency": currency,
        "value": price,
        "amountdate": datestr,
    }


def fixup_price2(date, currency, value):
    """Fixup price."""
    return create_signed_amount(
        currency=currency,
        value=value,
        amountdate=date,
    )


def create_amount(date, price):
    value, currency = morgan_price(price)
    return fixup_price2(date, currency, value)


def sum_amounts(amounts, positive_ok=True, negative_ok=True, negate=False):
    if len(amounts) == 0:
        return None

    expect_currency = amounts[0].currency
    expect_amountdate = amounts[0].amountdate

    sum = Decimal(0)

    for a in amounts:
        verify_sign(a.value, positive_ok, negative_ok)
        if a.currency != expect_currency:
            raise ValueError("Mixing currencies in sum_amount()")
        if a.amountdate != expect_amountdate:
            raise ValueError("Summing amounts for different days")

        sum += a.value

    if negate:
        sum *= -1

    return create_signed_amount(
        currency=expect_currency,
        value=sum,
        amountdate=expect_amountdate,
    )


def fixup_date(morgandate):  # noqa: C901
    """Do this explicitly here to learn about changes in the export format"""
    m = re.fullmatch(r"""(\d+)-([A-Z][a-z][a-z])-(20\d\d)""", morgandate)
    if m:
        day = f"{int(m.group(1)):02d}"
        textmonth = m.group(2)
        year = m.group(3)

        if textmonth == "Jan":
            return f"{year}-01-{day}"
        elif textmonth == "Feb":
            return f"{year}-02-{day}"
        elif textmonth == "Mar":
            return f"{year}-03-{day}"
        elif textmonth == "Apr":
            return f"{year}-04-{day}"
        elif textmonth == "May":
            return f"{year}-05-{day}"
        elif textmonth == "Jun":
            return f"{year}-06-{day}"
        elif textmonth == "Jul":
            return f"{year}-07-{day}"
        elif textmonth == "Aug":
            return f"{year}-08-{day}"
        elif textmonth == "Sep":
            return f"{year}-09-{day}"
        elif textmonth == "Oct":
            return f"{year}-10-{day}"
        elif textmonth == "Nov":
            return f"{year}-11-{day}"
        elif textmonth == "Dec":
            return f"{year}-12-{day}"

    raise ValueError(f'Illegal date: "{morgandate}"')


def fixup_date2(morgandate):
    m = re.fullmatch(r"""(\S+)\s+(\d+), (20\d\d)""", morgandate)
    if m:
        textmonth = m.group(1)
        day = f"{int(m.group(2)):02d}"
        year = m.group(3)

        if textmonth == "January":
            return f"{year}-01-{day}"
        elif textmonth == "February":
            return f"{year}-02-{day}"
        elif textmonth == "March":
            return f"{year}-03-{day}"
        elif textmonth == "April":
            return f"{year}-04-{day}"
        elif textmonth == "May":
            return f"{year}-05-{day}"
        elif textmonth == "June":
            return f"{year}-06-{day}"
        elif textmonth == "July":
            return f"{year}-07-{day}"
        elif textmonth == "August":
            return f"{year}-08-{day}"
        elif textmonth == "September":
            return f"{year}-09-{day}"
        elif textmonth == "October":
            return f"{year}-10-{day}"
        elif textmonth == "November":
            return f"{year}-11-{day}"
        elif textmonth == "December":
            return f"{year}-12-{day}"

    raise ValueError(f'Illegal date 2: "{morgandate}"')


def getitem(row, colname):
    """Get a named item from a row, or None if nothing there"""
    if colname not in row:
        return None
    item = row[colname]
    if isinstance(item, float):
        if math.isnan(item):
            return None
        return Decimal(f"{item}")
    if isinstance(item, str) and item == "":
        return None
    return item


def getitems(row, *colnames):
    ok = True
    rc = []
    for cn in colnames:
        i = getitem(row, cn)
        rc.append(i)
        if i is None:
            ok = False
    rc.append(ok)
    return tuple(rc)


def getoptcolitem(row, column, default_value):
    """If a column exist, return its value, otherwise the default value"""
    if column in row:
        item = row[column]
        if item is not None and item != "":
            return item
    return default_value


def parse_rsu_holdings_table(state, recs):
    state.symbol = "CSCO"  # Fail on other types of shares
    for row in recs:
        # print(f'RSU-Holdings: {row}')
        fund, date, buy_price, qty, ok = getitems(
            row,
            "Fund",
            "Acquisition Date",
            "Cost Basis Per Share *",
            "Total Shares You Hold",
        )
        if ok:
            if not re.fullmatch(r"""CSCO\s.*""", fund):
                raise ValueError(f"Non-Cisco RSU shares: {fund}")
            date = fixup_date(date)
            qty = Decimal(qty)
            price, currency = morgan_price(buy_price)
            purchase_price = fixup_price2(date, currency, price)
            state.entry_date = date
            state.deposit(qty, purchase_price, "RS", date)
            # print(f'### RSU {qty} {date} {price}')


def parse_espp_holdings_table(state, recs):
    for row in recs:
        # print(f'ESPP-Holdings: {row}')
        if state.parse_fund_symbol(row, "Grant Date"):
            continue

        offeringtype = getoptcolitem(row, "Offering Type", "Contribution")
        date, qty, ok = getitems(row, "Purchase Date", "Total Shares You Hold")
        if ok:
            assert state.symbol == "CSCO"
            date = fixup_date(date)
            state.entry_date = date
            qty = Decimal(qty)
            price = currency_converter[(state.symbol, state.entry_date)]
            if offeringtype == "Contribution":
                # Regular ESPP buy at reduced price
                purchase_price = fixup_price2(date, "ESPPUSD", price)
                state.deposit(qty, purchase_price, "ESPP", date)
                # print(f'### ESPP {qty} {date} {price}')
            elif offeringtype == "Dividend":
                # Reinvested dividend from ESPP shares at regular price
                purchase_price = fixup_price2(date, "USD", price)
                state.deposit(qty, purchase_price, "Reinvest", date)
            else:
                raise ValueError(f"Unexpected offering type: {offeringtype}")


def parse_rsu_activity_table(state, recs):  # noqa: C901
    ignore = {
        # The following are ignored, but it should be ok:
        # 'Cash Transfer Out' is for dividends moved from "Activity" table
        # to the RSU cash header of that table, and the 'Cash Transfer In'
        # is the counterpart in the RSU cash header.
        # The 'Transfer out' also shows up as a withdrawal, which is handled,
        # so we ignore that here too.
        "Cash Transfer In": True,
        "Cash Transfer Out": True,
        "Transfer out": True,
        "Historical Transaction": True,  # TODO: This should update cash-balance
    }

    for row in recs:
        if state.parse_fund_symbol(row, "Entry Date"):
            continue
        state.parse_entry_date(row)
        state.parse_activity(row)

        if state.parse_opening_value(row):
            continue

        if state.parse_closing_value(row):
            continue

        if state.parse_rsu_release(row):
            continue

        if state.parse_dividend_reinvest(row):
            continue

        if state.parse_sale(row):
            continue

        if state.parse_dividend_cash(row):
            continue

        if state.parse_tax_withholding(row):
            continue

        if state.parse_opening_balance(row):
            continue

        if state.parse_cash_adjustments(row):
            continue

        if state.parse_tax_returned(row):
            continue

        if state.activity in ignore:
            continue

        raise ValueError(f'Unknown RSU activity: "{state.activity}"')


def parse_espp_activity_table(state, recs):
    ignore = {
        "Adhoc Adjustment": True,
        "Transfer out": True,
        "Historical Transaction": True,
        "Wash Sale Adjustment": True,
        "Cash Transfer In": True,
        "Cash Transfer Out": True,
    }

    for row in recs:
        if state.parse_fund_symbol(row, "Entry Date"):
            continue
        state.parse_entry_date(row)
        state.parse_activity(row)

        if state.parse_opening_value(row):
            continue

        if state.parse_closing_value(row):
            continue

        if state.parse_dividend_reinvest(row):
            continue

        if state.parse_sale(row):
            continue

        if state.parse_deposit(row):
            continue

        if state.parse_dividend_cash(row):
            continue

        if state.parse_tax_withholding(row):
            continue

        if state.parse_tax_returned(row):
            continue

        if state.activity in ignore:
            continue

        raise ValueError(f'Unknown ESPP activity: "{state.activity}"')

    return state.transactions


def parse_espp_purchase_price_table(state, recs):
    for row in recs:
        if state.parse_fund_symbol(row, "Grant Date"):
            continue

        date, price, qty_bought, qty_kept, ok = getitems(
            row,
            "Purchase Date",
            "Purchase Price",
            "Shares Purchased",
            "Total Shares You Hold",
        )
        if ok:
            qty_bought = Decimal(morgan_qty(qty_bought))
            qty_kept = Decimal(morgan_qty(qty_kept))
            assert qty_bought > 0
            assert qty_kept <= qty_bought

            date = fixup_date(date)
            price, currency = morgan_price(price)
            assert currency == "USD"
            if date in state.espp_purchase_date2price:
                pass
            else:
                amount = Amount(currency=currency, value=price, amountdate=date)
                state.espp_purchase_date2price[date] = amount


class Withdrawal:
    """Given three tables for withdrawal, extract information we need"""

    def __init__(self, wd, sb, np):  # noqa: C901
        self.wd = wd
        self.sb = sb
        self.np = np

        self.description = "Withdrawal"
        self.is_transfer = False
        self.is_wire = False
        self.has_wire_fee = False

        assert self.wd.data[3][2] == "Settlement Date:"
        self.settlement_date = fixup_date(self.wd.data[3][3])
        self.withdrawal_date = fixup_date2(self.wd.header[0][0])

        assert self.wd.data[3][0] == "Fund"
        self.fund = self.wd.data[3][1]
        m = re.fullmatch(r"""([A-Za-z]+)\s+-.*""", self.fund)
        if not m:
            raise ValueError(f"Unexpected symbol format: {self.fund}")
        self.symbol = m.group(1)

        gross = []
        fees = []
        net = []

        for row in self.sb.rows:
            if "Gross Proceeds" in row[0]:
                gross.append(create_amount(self.settlement_date, row[1]))
            if "Fee" in row[0]:
                fees.append(create_amount(self.settlement_date, row[1]))
            if "Wire Fee" in row[0]:
                has_wire_fee = True

        m = re.fullmatch(r"""Net Proceeds: (.*)""", self.np.data[0][0])
        if m:
            net.append(create_amount(self.settlement_date, m.group(1)))

        assert len(gross) == 1
        assert len(net) == 1

        self.gross_amount = sum_amounts(gross)
        self.fees_amount = sum_amounts(fees, positive_ok=False)
        self.net_amount = sum_amounts(net, negative_ok=False, negate=True)

        assert self.wd.data[5][0] == "Delivery Method:"
        if "Transfer funds via wire" in self.wd.data[5][1]:
            self.is_wire = True
        if "Electronic Funds Transfer" in self.wd.data[5][1]:
            self.is_wire = True
        if "Historical sale of shares" in self.wd.data[5][1] and has_wire_fee:
            self.is_wire = True
        if "Deposit funds into my Morgan Stanley" in self.wd.data[5][1]:
            self.description = "Transfer to Morgan Stanley account"
            self.is_transfer = True
        if self.is_wire:
            self.description = "Wire-transfer"


def parse_withdrawal_sales(state, sales):
    """Withdrawals from sale of shares"""
    for wd, sb, np in sales:
        w = Withdrawal(wd, sb, np)
        state.record_sales_withdrawal(w)
        if w.is_wire:
            assert w.symbol != "Cash"  # No Cash-fund for sale withdrawals
            state.wire_transfer(w.settlement_date, w.net_amount, w.fees_amount)
        elif w.is_transfer:
            pass
        else:
            raise ValueError(
                f"Sales withdrawal w/o wire-transfer: wd={wd.data} sb={sb.data} np={np.data}"
            )


def parse_withdrawal_proceeds(state, proceeds):
    """Withdrawal of accumulated Cash (it seems)"""
    for wd, pb, np in proceeds:
        w = Withdrawal(wd, pb, np)
        if w.is_wire:
            assert w.symbol == "Cash"  # Proceeds withdrawal is for cash
            state.wire_transfer(w.withdrawal_date, w.net_amount, w.fees_amount)
        elif w.is_transfer:
            state.cashadjust(w.withdrawal_date, w.net_amount, w.description)
        else:
            raise ValueError(
                f"Proceeds withdrawal w/o wire-transfer: wd={wd.data} pb={pb.data} np={np.data}"
            )


def decode_headers(mi):
    """Force a MultiIndex or Index object into a plain array-of-arrays"""
    rc = []
    if isinstance(mi, MultiIndex):
        for lvl in range(0, mi.nlevels):
            line = []
            for n in range(0, mi.levshape[lvl]):
                line.append(str(mi[n][lvl]))
            rc.append(line)
    elif isinstance(mi, Index):
        rc.append([str(x) for x in mi.values])
    return rc


def istag(elem, tag):
    if not isinstance(elem.tag, str):
        return False
    m = re.fullmatch(r"""\{(.*)\}(.*)""", elem.tag)
    if m:
        standard = m.group(1)  # noqa: F841
        tagname = m.group(2)
        if tagname == tag:
            return True
    return False


def elem_enter(elem, tag):
    for x in elem:
        if istag(x, tag):
            return x
    return None


def elem_filter(elem, tag):
    rc = []
    for e in elem:
        if istag(e, tag):
            rc.append(e)
    return rc


def fixuptext(text):
    if text is None:
        return None

    substitute = {
        ord("\t"): " ",
        ord("\n"): " ",
        ord("\r"): " ",
        0xA0: " ",  # Non-breaking space => Regular space
    }
    rc = text.translate(substitute)
    while True:
        m = re.fullmatch(r"""(.*)\s\s+(.*)""", rc)
        if m:
            rc = f"{m.group(1)} {m.group(2)}"
            continue
        break

    m = re.fullmatch(r"""\s*(.*\S)\s*""", rc)
    if m:
        rc = m.group(1)

    if rc == " ":
        return ""
    return rc


def get_rawtext(elem):
    rc = ""
    if elem.text is not None:
        rc += f" {elem.text}"
    if elem.tail is not None:
        rc += f" {elem.tail}"
    for x in elem:
        rc += f" {get_rawtext(x)}"
    return rc


def get_elem_text(elem):
    return fixuptext(get_rawtext(elem))


def decode_data(table):
    """Place table-data into a plain array-of-arrays"""
    tb = elem_enter(table, "tbody")
    if tb is None:
        return None

    rc = []
    for tr in elem_filter(tb, "tr"):
        row = []
        for te in tr:
            if istag(te, "th") or istag(te, "td"):
                row.append(get_elem_text(te))
        rc.append(row)

    return rc


def array_match_2d(candidate, template):
    """Match a candidate array-of-arrays against a template to match it.

    The template may contain None entries, which will match any candidate
    entry, or it may contain a compiled regular expression - and the result
    will be the candidate data matched by the regex parenthesis. A simple
    string will need to match completely, incl. white-spaces."""

    if candidate is None or len(candidate) < len(template):
        return None

    rc = []
    for cl, tl in zip(candidate, template):
        if len(cl) != len(tl):
            return None
        line = []
        for n, ci, ti in zip(range(1, 1000), cl, tl):
            if ti is None:
                line.append(str(ci))
                continue
            if isinstance(ti, re.Pattern):
                m = ti.fullmatch(ci)
                if m:
                    line.append(m.group(1))
                    continue
                return None
            if ci == ti:
                line.append(ci)
                continue
            return None
        rc.append(line)

    return rc


def header_match(table, search_header, hline=0):
    """Use a search-template to look for tables with headers that match.

    The search-template is give to 'array_match_2d' above for matching.
    When a table is matched, the column-names are established from the
    header-line given by 'hline' (default 0)."""
    result = array_match_2d(table.data, search_header)
    if result is None:
        return False
    table.header = result
    table.colnames = result[hline]
    for idx, colname in zip(range(0, 1000), table.colnames):
        table.colname2idx[colname] = idx

    numheaderlines = len(search_header)
    table.rows = table.data[numheaderlines:]

    return True


def find_tables_by_header(tables, search_header, hline=0):
    """Given a header-template for matching, return all matching tables"""
    rc = []
    for t in tables:
        if header_match(t, search_header, hline):
            rc.append(t)
    return rc


def parse_account_summary_html(tables):
    search_account_summary = [
        [""],
        [None, "", re.compile(r"""Account Summary Statement(.*)""")],
    ]
    summary = find_tables_by_header(tables, search_account_summary, 1)

    if len(summary) == 0:
        # Try again to find the info in 2023 statements...
        search_account_summary = [
            [""],
            [None, "", re.compile(r"""Account Summary Summary (.*)""")],
        ]
        summary = find_tables_by_header(tables, search_account_summary, 1)

    assert len(summary) == 1
    period = summary[0].data[1][2]
    m = re.fullmatch(r""".*Period\s*:\s+(\S+)\s+to\s+(\S+).*""", period)
    if m:
        return (fixup_date(m.group(1)), fixup_date(m.group(2)))
    raise ValueError("Failed to parse Account Summary Statement")


def parse_rsu_holdings_html(all_tables, state):
    """Look for RSU holdings table and include historic holdings as deposits"""
    search_rsu_holdings = [
        ["Summary of Stock/Shares Holdings"],
        [
            "Fund",
            "Acquisition Date",
            "Lot",
            "Capital Gain Impact",
            "Gain/Loss",
            "Cost Basis *",
            "Cost Basis Per Share *",
            "Total Shares You Hold",
            "Current Price per Share",
            "Current Value",
        ],
        ["Type of Money: Employee"],
    ]

    rsu_holdings = find_tables_by_header(all_tables, search_rsu_holdings, 1)
    if len(rsu_holdings) == 0:
        return

    print(f"### LEN(rsu_holdings)={len(rsu_holdings)}")
    assert len(rsu_holdings) == 1

    # print('#### Found RSU holdings')

    parse_rsu_holdings_table(state, rsu_holdings[0].to_dict())


def parse_espp_holdings_html(all_tables, state, year):
    """Parse ESPP holdings table and include historic holdings as deposits"""

    search1 = [
        ["Purchase History for Stock/Shares"],
        [
            "Grant Date",
            "Subscription Date",
            "Subscription Date FMV",
            "Purchase Date",
            "Purchase Date FMV",
            "Purchase Price",
            "Qualification Date *",
            "Shares Purchased",
            "Total Shares You Hold",
            "Current Share Price",
            "Current Value",
        ],
    ]

    search2 = [
        ["Purchase History for Stock/Shares"],
        [
            "Grant Date",
            "Offering Type",
            "Subscription Date",
            "Subscription Date FMV",
            "Purchase Date",
            "Purchase Date FMV",
            "Purchase Price",
            "Qualification Date *",
            "Shares Purchased",
            "Total Shares You Hold",
            "Current Share Price",
            "Current Value",
        ],
    ]

    espp_holdings = find_tables_by_header(all_tables, search1, 1)
    if len(espp_holdings) == 0:
        espp_holdings = find_tables_by_header(all_tables, search2, 1)

    if len(espp_holdings) == 0:
        print(f"No ESPP holdings found for {year}")
        return

    assert len(espp_holdings) == 1

    parse_espp_purchase_price_table(state, espp_holdings[0].to_dict())
    parse_espp_holdings_table(state, espp_holdings[0].to_dict())


def parse_rsu_activity_html(all_tables, state):
    """Look for the RSU table and parse it"""
    search_rsu_header = [
        ["Activity"],
        [
            "Entry Date",
            "Activity",
            "Type of Money",
            "Cash",
            "Number of Shares",
            "Share Price",
            "Book Value",
            "Market Value",
        ],
    ]

    rsu = find_tables_by_header(all_tables, search_rsu_header, 1)

    print(f"#### RSU activity tables found: {len(rsu)}")

    if len(rsu) == 0:
        return

    assert len(rsu) == 1
    parse_rsu_activity_table(state, rsu[0].to_dict())


def parse_espp_activity_html(all_tables, state):
    """Look for the ESPP activity/transaction table and parse it"""
    any = re.compile(r"""(.*)""")
    search_espp_header = [
        ["Activity"],
        [
            "Entry Date",
            "Activity",
            "Cash",
            "Number of Shares",
            "Share Price",
            "Market Value",
            any,
        ],
    ]

    espp = find_tables_by_header(all_tables, search_espp_header, 1)

    if len(espp) == 0:
        search_espp_header = [
            ["Activity"],
            [
                "Entry Date",
                "Activity",
                "Cash",
                "Number of Shares",
                "Share Price",
                "Market Value",
            ],
        ]

        espp = find_tables_by_header(all_tables, search_espp_header, 1)

    print(f"### ESPP tables found: {len(espp)}")

    if len(espp) == 1:
        parse_espp_activity_table(state, espp[0].to_dict())
    elif len(espp) != 0:
        raise ValueError(f"Expected 0 or 1 ESPP tables, got {len(espp)}")


def parse_withdrawals_html(all_tables, state):
    search_withdrawal_header = [[re.compile(r"""Withdrawal on (.*)""")]]
    search_salebreakdown = [[re.compile(r"""\s*(Sale Breakdown)""")]]
    search_proceedsbreakdown = [[re.compile(r"""\s*(Proceeds Breakdown)""")]]
    search_net_proceeds = [[None]]

    withdrawals = find_tables_by_header(all_tables, search_withdrawal_header)

    sales = []
    proceeds = []
    netproceeds = []  # noqa: F841
    for wd in withdrawals:
        nexttab = [all_tables[wd.idx + 1]]
        nextnexttab = [all_tables[wd.idx + 2]]

        np = find_tables_by_header(nextnexttab, search_net_proceeds)
        if len(np) != 1:
            raise ValueError(f"Unable to parse net-proceeds: {nextnexttab}")

        sb = find_tables_by_header(nexttab, search_salebreakdown)
        if len(sb) == 1:
            sales.append((wd, sb[0], np[0]))
            continue

        pb = find_tables_by_header(nexttab, search_proceedsbreakdown)
        if len(pb) == 1:
            proceeds.append((wd, pb[0], np[0]))
            continue

        raise ValueError('Unable to parse "Sale/Proceeds Breakdown"')

    parse_withdrawal_sales(state, sales)
    parse_withdrawal_proceeds(state, proceeds)


def parse_cash_holdings_html(all_tables, state, year):
    search_cash_holding_header = [
        ["Summary of Cash Holdings"],
        ["Fund", "Current Value"],
    ]
    cashtabs = find_tables_by_header(all_tables, search_cash_holding_header)
    total = Decimal("0.00")
    for ct in cashtabs:
        for row in ct.rows:
            if len(row) == 2 and row[0] == "Cash - USD":
                value, currency = morgan_price(row[1])
                assert currency == "USD"
                total += Decimal(value)
                print(f"### Cash: {value}")
    print(f"### Cash holdings: {total}")
    cash = fixup_price2(f"{year}-12-31", "USD", total)
    state.cashadjust(f"{year}-12-31", cash, f"Closing balance {year}")


def compute_transaction_deltas(transes):
    csco_delta = Decimal("0.00")
    cash_delta = Decimal("0.00")
    for t in transes:
        if t.type == EntryTypeEnum.SELL:
            csco_delta += t.qty
            cash_delta += t.amount.value
        elif t.type == EntryTypeEnum.WIRE:
            cash_delta += t.amount.value
            if t.fee:
                cash_delta += t.fee.value
        elif t.type == EntryTypeEnum.TAX:
            cash_delta += t.amount.value
        elif t.type == EntryTypeEnum.DIVIDEND:
            cash_delta += t.amount.value
        elif t.type == EntryTypeEnum.DEPOSIT:
            csco_delta += t.qty
        elif t.type == EntryTypeEnum.CASHADJUST:
            cash_delta += t.amount.value
        elif t.type == EntryTypeEnum.TAXSUB:
            cash_delta += t.amount.value
        elif t.type == EntryTypeEnum.DIVIDEND_REINV:
            cash_delta += t.amount.value
        else:
            print(f"Not handled: {t}")
            assert False
    return csco_delta, cash_delta


def morgan_html_import(html_fd, filename):
    """Parse Morgan Stanley HTML table file."""

    document = html5lib.parse(html_fd)
    all_tables = find_all_tables(document)

    state = ParseState(filename)

    start_period, end_period = parse_account_summary_html(all_tables)

    # Look for start "year-01-01" and end "year-12-31" for some 'year'
    # and assume this is the transaction file for that tax-year
    year = int(end_period[0:4])
    if (
        start_period[0:5] == end_period[0:5]
        and start_period[5:10] == "01-01"
        and end_period[5:10] == "12-31"
    ):
        print("Parse withdrawals ...")
        parse_withdrawals_html(all_tables, state)
        print("Parse RSU activity ...")
        parse_rsu_activity_html(all_tables, state)
        print("Parse ESPP activity ...")
        parse_espp_activity_html(all_tables, state)
        state.flush_dividend()
    elif end_period[4:10] == "-12-31":
        # Assume this file will be used to find holdings up to the EOY in
        # question. The Morgan statment must *not* start at Jan 1st of
        # the same year, or else the file will be confused with the
        # transaction file for the tax-year (in above if-section)
        # Parse the holdings tables to produce deposits to establish the
        # holdings at the end of the year.
        print("Parse RSU holdings ...")
        parse_rsu_holdings_html(all_tables, state)
        print("Parse ESPP holdings ...")
        parse_espp_holdings_html(all_tables, state, year)
        print("Parse Cash holdings ...")
        parse_cash_holdings_html(all_tables, state, year)
    else:
        raise ValueError(f"Period {start_period} - {end_period} is unexpected")

    print("Done")

    print(
        f">>> Sum Opening value: ${state.opening_value_cash} qty={state.opening_value_shares}"
    )
    print(
        f">>> Sum Closing value: ${state.closing_value_cash} qty={state.closing_value_shares}"
    )

    # This seems to not be the right thing to do for current test-files.
    # Maybe reporting dates from Morgan has changed? It doesn't look like
    # it has, so the fear is that neither the withdrawal-date, nor the
    # settlement-date is the actual date of a sale: This would complicate
    # the situation for sales around the dividend exdate, as we don't
    # know if the sale happened before or after exdate. It would be
    # possible to use dividend payout records for guidance, but the date
    # of sale would then need to be moved (for at least some shares) to
    # patch the sale. This would be more work and generally undesirable.
    # state.fixup_selldates()

    # The transactions of the tax-year
    transes = sorted(state.transactions, key=lambda d: d.date)

    # Check if our transaction entries sums up to the expected deltas
    delta_csco_qty, delta_cash = compute_transaction_deltas(transes)

    calculated_closing_cash = state.opening_value_cash + delta_cash
    error = state.closing_value_cash - calculated_closing_cash
    if not close_to_zero(error, "0.01"):
        logger.warning(
            f"Calculated yearly change to cash is different from expected by ${error}"
        )

    calculated_closing_shares = state.opening_value_shares + delta_csco_qty
    error = state.closing_value_shares - calculated_closing_shares
    if not close_to_zero(error, "0.0001"):
        logger.warning(
            f"Calculated yearly change to shares is different from expected by {error} shares"
        )

    # The amount of cash in USD at the beginning of the tax-year
    opening_cash = Decimal(state.opening_value_cash)

    # The amount of cash in USD at the end of the tax-year
    closing_cash = Decimal(state.closing_value_cash)

    # Collect cash amounts from above, and CSCO shares
    balances = TransactionTaxYearBalances(
        opening_cash=opening_cash,
        closing_cash=closing_cash,
        opening_value_symbol_qty={"CSCO": state.opening_value_shares},
        closing_value_symbol_qty={"CSCO": state.closing_value_shares},
    )

    return Transactions(
        fromdate=start_period,
        enddate=end_period,
        opening_balance=balances,
        transactions=transes,
    )


def read(html_file, filename="") -> Transactions:
    """Main entry point of plugin. Return normalized Python data structure."""
    return morgan_html_import(html_file, filename)
