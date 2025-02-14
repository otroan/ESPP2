"""
Schwab JSON normalizer.
"""

# pylint: disable=invalid-name, too-many-locals, too-many-branches

from datetime import date
import math
import json
from decimal import Decimal, InvalidOperation
import logging
import dateutil.parser as dt
from espp2.datamodels import (
    Transactions,
    Wire,
    Amount,
    Taxsub,
    PositiveAmount,
    NegativeAmount,
    Sell,
    Deposit,
    Dividend,
    Dividend_Reinv,
    Tax,
    Transfer,
    Cashadjust,
)

logger = logging.getLogger(__name__)


def get_saleprice(csv_item):
    for e in csv_item["TransactionDetails"]:
        return e["Details"]["SalePrice"]


def get_grossproceeds(csv_item):
    total = Decimal("0.00")
    for e in csv_item["TransactionDetails"]:
        if e["Details"]["Shares"] == "0":
            continue
        price = e["Details"]["GrossProceeds"]
        total += Decimal(price.replace("$", "").replace(",", ""))

    datestr = fixup_date(csv_item["Date"])
    return Amount(amountdate=datestr, currency="USD", value=total)


def get_purchaseprice(csv_item):
    # RS
    subdata = csv_item["TransactionDetails"][0]["Details"]
    description = csv_item["Description"]
    if description == "RS" and subdata["VestFairMarketValue"] != "":
        return subdata["VestFairMarketValue"]
    # ESPP
    if description == "ESPP" and subdata["PurchaseFairMarketValue"] != "":
        return subdata["PurchaseFairMarketValue"]

    # Div Reinv
    if description == "Div Reinv" and subdata["PurchasePrice"] != "":
        return subdata["PurchasePrice"]

    raise ValueError(f"Unknown purchase price for {csv_item}")


def fixup_date(datestr):
    """Fixup date"""
    d = dt.parse(datestr)
    return d.strftime("%Y-%m-%d")


def fixup_date_as_date(datestr) -> date:
    """Fixup date"""
    d = dt.parse(datestr)
    return d.date()


# currency_converter = FMV()


def fixup_price(datestr, currency, pricestr) -> Amount:
    """Fixup price."""
    price = Decimal(pricestr.replace("$", "").replace(",", ""))
    return PositiveAmount(
        amountdate=datestr,
        currency=currency,
        value=price,
    )


def fixup_price_negative(datestr, currency, pricestr) -> Amount:
    """Fixup price."""
    price = Decimal(pricestr.replace("$", "").replace(",", ""))
    return NegativeAmount(
        amountdate=datestr,
        currency=currency,
        value=price,
    )


def fixup_number(numberstr):
    """Convert string to number."""
    try:
        return Decimal(numberstr)
    except ValueError:
        return ""


def sale(csv_item, source):
    """Process sale"""
    d = fixup_date(csv_item["Date"])
    try:
        fee = fixup_price_negative(d, "USD", csv_item["FeesAndCommissions"])
    except InvalidOperation:
        fee = None

    saleprice = fixup_price(d, "USD", get_saleprice(csv_item))
    grossproceeds = fixup_price(d, "USD", csv_item["Amount"])
    g = get_grossproceeds(csv_item)
    g += fee

    if not math.isclose(g.value, grossproceeds.value, abs_tol=5):
        logger.error(
            f"Gross proceeds mismatch: {g} != {grossproceeds}. {d} {csv_item['Description']}"
        )
        grossproceeds = g
    qty = fixup_number(csv_item["Quantity"])

    return Sell(
        date=d,
        symbol=csv_item["Symbol"],
        description=csv_item["Description"],
        qty=qty * -1,
        sale_price=saleprice,
        amount=grossproceeds,
        fee=fee,
        source=source,
    )


def tax_withholding(csv_item, source):
    """Process tax withholding"""
    d = fixup_date(csv_item["Date"])
    amount = fixup_price_negative(d, "USD", csv_item["Amount"])
    return Tax(
        date=d,
        symbol=csv_item["Symbol"],
        description=csv_item["Description"],
        amount=amount,
        source=source,
    )


def dividend(csv_item, source):
    """Process dividend"""
    d = fixup_date(csv_item["Date"])
    amount = fixup_price(d, "USD", csv_item["Amount"])
    return Dividend(
        date=d,
        symbol=csv_item["Symbol"],
        description=csv_item["Description"],
        amount=amount,
        source=source,
    )


def dividend_reinvested(csv_item, source):
    """Process dividend reinvested"""
    d = fixup_date(csv_item["Date"])
    amount = fixup_price_negative(d, "USD", csv_item["Amount"])

    return Dividend_Reinv(
        date=d,
        symbol=csv_item["Symbol"],
        description=csv_item["Description"],
        amount=amount,
        source=source,
    )


def tax_reversal(csv_item, source):
    """Process tax reversal"""
    d = fixup_date(csv_item["Date"])
    amount = fixup_price(d, "USD", csv_item["Amount"])
    return Taxsub(
        date=d,
        symbol=csv_item["Symbol"],
        description=csv_item["Description"],
        amount=amount,
        source=source,
    )


def wire(csv_item, source):
    """Process wire"""
    d = fixup_date(csv_item["Date"])
    if csv_item["FeesAndCommissions"]:
        fee = fixup_price_negative(d, "USD", csv_item["FeesAndCommissions"])
    else:
        fee = fixup_price_negative(d, "USD", "$0.0")

    amount = fixup_price(d, "USD", csv_item["Amount"])
    return Wire(
        date=d,
        description=csv_item["Description"],
        amount=amount,
        fee=fee,
        source=source,
        currency="USD",
    )


def deposit(csv_item, source):
    """Process deposit"""
    purchase_date = None
    if csv_item["Description"] == "ESPP":
        purchase_date = fixup_date(
            csv_item["TransactionDetails"][0]["Details"]["PurchaseDate"]
        )
        d = purchase_date
        currency = "ESPPUSD"
    else:
        d = fixup_date(csv_item["Date"])
        currency = "USD"
    qty = fixup_number(csv_item["Quantity"])
    purchase_price = fixup_price(d, currency, get_purchaseprice(csv_item))

    return Deposit(
        date=d,
        symbol=csv_item["Symbol"],
        description=csv_item["Description"],
        qty=qty,
        purchase_date=purchase_date,
        purchase_price=purchase_price,
        source=source,
    )


def not_implemented(csv_item, source):
    """Process not implemented"""
    raise NotImplementedError(f"Action \"{csv_item['Action']}\" not implemented")


def transfer(csv_item, source):
    """Process transfer"""
    d = fixup_date(csv_item["Date"])
    if csv_item["FeesAndCommissions"]:
        fee = fixup_price(d, "USD", csv_item["FeesAndCommissions"])
    else:
        fee = fixup_price(d, "USD", "$0.0")
    return Transfer(
        date=d,
        description=csv_item["Description"],
        symbol=csv_item["Symbol"],
        qty=-fixup_number(csv_item["Quantity"]),
        fee=fee,
        source=source,
    )


def exercise_and_sell(csv_item, source):
    """Stock Options exercise and sell"""
    d = fixup_date(csv_item["Date"])
    if csv_item["FeesAndCommissions"]:
        fee = fixup_price(d, "USD", csv_item["FeesAndCommissions"], change_sign=True)
    else:
        fee = fixup_price(d, "USD", "$0.0")

    amount = fixup_price(d, "USD", csv_item["Amount"])
    return Wire(
        date=d,
        description=csv_item["Description"],
        amount=Amount(**amount),
        fee=NegativeAmount(**fee),
        source=source,
        currency="USD",
    )


def journal(csv_item, source):
    """Process journal"""
    # Stocks
    if csv_item["Quantity"]:
        return transfer(csv_item, source)

    # Wires
    return wire(csv_item, source)


def adjustment(csv_item, source):
    """Process adjustment"""
    d = fixup_date(csv_item["Date"])
    if csv_item["FeesAndCommissions"]:
        fee = fixup_price(d, "USD", csv_item["FeesAndCommissions"])
    else:
        fee = fixup_price(d, "USD", "$0.0")
    return Cashadjust(
        date=fixup_date(csv_item["Date"]),
        description=csv_item["Description"],
        amount=fixup_price(d, "USD", csv_item["Amount"]),
        source=source,
    )


dispatch = {
    "Deposit": deposit,
    "Wire Transfer": wire,
    "MWI": wire,
    "Sale": sale,
    "Quick Sale": sale,  # "Quick Sale" is a "Sale"
    "Tax Withholding": tax_withholding,
    "Dividend": dividend,
    "Dividend Reinvested": dividend_reinvested,
    "Tax Reversal": tax_reversal,
    "Journal": journal,
    "Service Fee": not_implemented,
    "Adjustment": adjustment,
    "Transfer": transfer,
    "Exercise and Sell": exercise_and_sell,
}


def is_date_in_range(record_date: date, fromdate: date, todate: date) -> bool:
    """Check if a record's date falls within the date range."""
    return fromdate <= record_date <= todate


def get_record_date(csv_item) -> date:
    """Get the relevant date for a record based on its type."""
    # For ESPP deposits, use purchase date
    if csv_item["Description"] == "ESPP":
        return fixup_date_as_date(
            csv_item["TransactionDetails"][0]["Details"]["PurchaseDate"]
        )

    # For RS (Restricted Stock), use vest date if available
    if csv_item["Description"] == "RS":
        details = csv_item["TransactionDetails"][0]["Details"]
        if "VestDate" in details and details["VestDate"]:
            return fixup_date_as_date(details["VestDate"])

    # For all other records, use transaction date
    return fixup_date_as_date(csv_item["Date"])


def read(json_file, filename="") -> Transactions:
    """Main entry point of plugin. Return normalized Python data structure."""

    data = json.load(json_file)
    records = []
    fromdate = fixup_date_as_date(data["FromDate"])
    todate = fixup_date_as_date(data["ToDate"])

    # Check if the date range is valid
    # if not is_date_in_range(record_fromdate, fromdate, todate) and not is_date_in_range(
    #     record_todate, fromdate, todate
    # ):
    #     logger.error(f"Date range is invalid: {record_fromdate} to {record_todate}")
    #     raise ValueError(f"Date range is invalid: {record_fromdate} to {record_todate}")

    for t in data["Transactions"]:
        logger.debug("Processing record: %s", t)

        # Get the relevant date before processing
        # record_date = get_record_date(t)
        # print(f"Record date: {record_date}")
        # Create the record object
        r = dispatch[t["Action"]](t, source=f"schwab:{filename}")
        records.append(r)

    return Transactions(transactions=records, fromdate=fromdate, todate=todate)
