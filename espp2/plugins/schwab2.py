"""
Schwab2 CSV normalizer.
"""

# pylint: disable=invalid-name, too-many-locals, too-many-branches

import csv
from decimal import Decimal
import codecs
import io
import logging
import dateutil.parser as dt
from espp2.fmv import FMV
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
)

logger = logging.getLogger(__name__)


def schwab_csv_import(fd):
    """Parse Schwab2 CSV file."""

    data = []

    # Fastapi passes in binary file and CLI passes in a TextIOWrapper
    if isinstance(fd, io.TextIOWrapper):
        reader = csv.reader(fd)
    else:
        reader = csv.reader(codecs.iterdecode(fd, "utf-8"))

    try:
        header = next(reader)
        assert header == (
            [
                "Date",
                "Action",
                "Symbol",
                "Description",
                "Quantity",
                "FeesAndCommissions",
                "DisbursementElection",
                "Amount",
                "Type",
                "Shares",
                "SalePrice",
                "SubscriptionDate",
                "SubscriptionFairMarketValue",
                "PurchaseDate",
                "PurchasePrice",
                "PurchaseFairMarketValue",
                "DispositionType",
                "GrantId",
                "VestDate",
                "VestFairMarketValue",
                "GrossProceeds",
                "AwardDate",
                "AwardId",
            ]
        )

        def field(x):
            return header.index(x)

        data = []
        while True:
            row = next(reader)
            if len(row) == 1:
                continue
            if row[field("Date")] == "":
                # Sub-section
                if "subdata" not in data[-1]:
                    data[-1]["subdata"] = []
                data[-1]["subdata"].append(
                    {header[v].upper(): k for v, k in enumerate(row) if v != 0}
                )
            else:
                data.append({header[v].upper(): k for v, k in enumerate(row)})
    except StopIteration:
        pass
    return data


def fixup_date(datestr):
    """Fixup date"""
    d = dt.parse(datestr)
    return d.strftime("%Y-%m-%d")


currency_converter = FMV()


def fixup_price(datestr, currency, pricestr, change_sign=False):
    """Fixup price."""
    price = Decimal(pricestr.replace("$", "").replace(",", ""))
    if change_sign:
        price = price * -1
    exchange_rate = currency_converter.get_currency(currency, datestr)
    return {
        "currency": currency,
        "value": price,
        "nok_exchange_rate": exchange_rate,
        "nok_value": price * exchange_rate,
    }


def fixup_number(numberstr):
    """Convert string to number."""
    try:
        return Decimal(numberstr)
    except ValueError:
        return ""


def get_purchaseprice(csv_item):
    # RS
    subdata = csv_item["subdata"][0]
    description = csv_item["DESCRIPTION"]
    if description == "RS" and subdata["VESTFAIRMARKETVALUE"] != "":
        return subdata["VESTFAIRMARKETVALUE"]
    # ESPP
    if description == "ESPP" and subdata["PURCHASEFAIRMARKETVALUE"] != "":
        return subdata["PURCHASEFAIRMARKETVALUE"]

    # Div Reinv
    if description == "Div Reinv" and subdata["PURCHASEPRICE"] != "":
        return subdata["PURCHASEPRICE"]

    raise ValueError(f"Unknown purchase price for {csv_item}")


def deposit(csv_item, source):
    """Process deposit"""
    purchase_date = None
    if csv_item["DESCRIPTION"] == "ESPP":
        purchase_date = fixup_date(csv_item["subdata"][0]["PURCHASEDATE"])
        d = purchase_date
    else:
        d = fixup_date(csv_item["DATE"])
    qty = fixup_number(csv_item["QUANTITY"])
    purchase_price = fixup_price(d, "USD", get_purchaseprice(csv_item))
    return Deposit(
        date=d,
        symbol=csv_item["SYMBOL"],
        description=csv_item["DESCRIPTION"],
        qty=qty,
        purchase_date=purchase_date,
        purchase_price=Amount(**purchase_price),
        source=source,
    )


def wire(csv_item, source):
    """Process wire"""
    d = fixup_date(csv_item["DATE"])
    if csv_item["FEESANDCOMMISSIONS"]:
        fee = fixup_price(d, "USD", csv_item["FEESANDCOMMISSIONS"])
    else:
        fee = fixup_price(d, "USD", "$0.0")

    amount = fixup_price(d, "USD", csv_item["AMOUNT"])
    return Wire(
        date=d,
        description=csv_item["DESCRIPTION"],
        amount=Amount(**amount),
        fee=NegativeAmount(**fee),
        source=source,
        currency="USD",
    )


def get_saleprice(csv_item):
    for e in csv_item["subdata"]:
        return e["SALEPRICE"]


def sale(csv_item, source):
    """Process sale"""
    d = fixup_date(csv_item["DATE"])
    fee = fixup_price(d, "USD", csv_item["FEESANDCOMMISSIONS"], change_sign=True)
    saleprice = fixup_price(d, "USD", get_saleprice(csv_item))
    grossproceeds = fixup_price(d, "USD", csv_item["AMOUNT"])
    qty = fixup_number(csv_item["QUANTITY"])

    return Sell(
        date=d,
        symbol=csv_item["SYMBOL"],
        description=csv_item["DESCRIPTION"],
        qty=qty * -1,
        sale_price=Amount(**saleprice),
        amount=Amount(**grossproceeds),
        fee=NegativeAmount(**fee),
        source=source,
    )


def tax_withholding(csv_item, source):
    """Process tax withholding"""
    d = fixup_date(csv_item["DATE"])
    amount = fixup_price(d, "USD", csv_item["AMOUNT"])

    return Tax(
        date=d,
        symbol=csv_item["SYMBOL"],
        description=csv_item["DESCRIPTION"],
        amount=amount,
        source=source,
    )


def dividend(csv_item, source):
    """Process dividend"""
    d = fixup_date(csv_item["DATE"])
    amount = fixup_price(d, "USD", csv_item["AMOUNT"])

    return Dividend(
        date=fixup_date(csv_item["DATE"]),
        symbol=csv_item["SYMBOL"],
        description=csv_item["DESCRIPTION"],
        amount=PositiveAmount(**amount),
        source=source,
    )


def dividend_reinvested(csv_item, source):
    """Process dividend reinvested"""
    d = fixup_date(csv_item["DATE"])
    amount = fixup_price(d, "USD", csv_item["AMOUNT"])

    return Dividend_Reinv(
        date=d,
        symbol=csv_item["SYMBOL"],
        description=csv_item["DESCRIPTION"],
        amount=Amount(**amount),
        source=source,
    )


def tax_reversal(csv_item, source):
    """Process tax reversal"""
    d = fixup_date(csv_item["DATE"])
    amount = fixup_price(d, "USD", csv_item["AMOUNT"])
    return Taxsub(
        date=d,
        symbol=csv_item["SYMBOL"],
        description=csv_item["DESCRIPTION"],
        amount=Amount(**amount),
        source=source,
    )


dispatch = {
    "Deposit": deposit,
    "Wire Transfer": wire,
    "Sale": sale,
    "Tax Withholding": tax_withholding,
    "Dividend": dividend,
    "Dividend Reinvested": dividend_reinvested,
    "Tax Reversal": tax_reversal,
    "Journal": wire,
}


def read(csv_file, filename="") -> Transactions:
    """Main entry point of plugin. Return normalized Python data structure."""
    csv_data = schwab_csv_import(csv_file)
    records = []
    for csv_item in csv_data:
        logger.debug("Processing record: %s", csv_item)
        r = dispatch[csv_item["ACTION"]](csv_item, source=f"schwab:{filename}")
        records.append(r)

    # sorted_transactions = sorted(newlist, key=lambda d: d['date'])
    return Transactions(transactions=records)
