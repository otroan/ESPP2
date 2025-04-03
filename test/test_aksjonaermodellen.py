import os
from espp2.main import tax_report
from espp2.transactions import plugin_read
from decimal import Decimal
from espp2.fmv import FMV
from espp2.fmv import todate
from datetime import datetime, date
from typing import Tuple, Union

# Store the original method
original_get_currency = FMV.get_currency

# Mock data for dividends
MOCK_DIVIDEND_DATA = {
    "fetched": "2025-04-03",
    "1901-09-09": {
        "date": "1901-08-08",
        "declarationDate": "1901-08-01",
        "paymentDate": "1901-09-09",
        "value": 0.50,
        "currency": "USD",
    },
    "1902-09-09": {
        "date": "1902-08-08",
        "declarationDate": "1902-08-01",
        "paymentDate": "1902-09-09",
        "value": 0.10,
        "currency": "USD",
    },
    "1903-09-09": {
        "date": "1903-08-08",
        "declarationDate": "1903-08-01",
        "paymentDate": "1903-09-09",
        "value": 0.10,
        "currency": "USD",
    },
}

MOCK_FUNDAMENTALS_DATA = {
    "fetched": "2025-04-02",
    "General": {
        "Code": "SEAM",
        "Name": "Skatteetaten Aksjonaermodell Example",
        "CountryName": "Norway",
        "CurrencyCode": "USD",
    },
}

MOCK_STOCK_DATA = {
    "fetched": "2025-04-02",
    "1900-12-31": 10.00,
    "1901-12-31": 10.00,
    "1902-12-31": 10.00,
    "1903-12-31": 10.00,
    "1904-12-31": 10.00,
}


def load_transactions(filename):
    base_dir = os.path.dirname(__file__)
    transfile = os.path.join(base_dir, filename)
    with open(transfile, "r", encoding="utf-8") as f:
        transactions = plugin_read(f, transfile, "schwab-json")
    return transactions


# Define the mock function for tax deduction rates
def mock_get_tax_deduction_rate(year):
    test_rates = {
        1901: Decimal("2.1"),
        1902: Decimal("2.5"),
        1903: Decimal("2.5"),
        1904: Decimal("2.5"),
    }
    if year in test_rates:
        return test_rates[year]
    # Raise an error for any unexpected year during this test
    raise ValueError(f"Unexpected year {year} requested in mock_get_tax_deduction_rate")


# Define the mock function for get_currency
def mock_fmv_get_currency(self, currency, date_union, target_currency="NOK"):
    date_obj, _ = self.extract_date(date_union)
    if currency == "USD" and date_obj.year <= 1904:
        return Decimal("10.000")
    return original_get_currency(self, currency, date_union, target_currency)


# Define the mock function for get_dividend
def mock_fmv_get_dividend(
    self, dividend: str, payment_date: Union[str, datetime]
) -> Tuple[date, date, Decimal]:
    dividends_only = {k: v for k, v in MOCK_DIVIDEND_DATA.items() if k != "fetched"}
    exdate = todate(dividends_only[payment_date]["date"])
    declarationdate = todate(dividends_only[payment_date]["declarationDate"])
    value = Decimal(str(dividends_only[payment_date]["value"]))
    return exdate, declarationdate, value


def mock_fmv_get_fundamentals(self, symbol: str) -> dict:
    return MOCK_FUNDAMENTALS_DATA


def mock_fmv_get_stock(self, item):
    symbol, itemdate = item
    print("ITEM", item)
    print("SYMBOL", symbol)
    print("ITEMDATE", itemdate)

    return Decimal(str(MOCK_STOCK_DATA[itemdate]))


def test_aksjonaermodellen(monkeypatch):
    # Patch the original function with our mock version for tax deduction
    monkeypatch.setattr(
        "espp2.portfolio.get_tax_deduction_rate", mock_get_tax_deduction_rate
    )
    monkeypatch.setattr("espp2.fmv.FMV.get_currency", mock_fmv_get_currency)
    monkeypatch.setattr("espp2.fmv.FMV.__getitem__", mock_fmv_get_stock)
    monkeypatch.setattr("espp2.fmv.FMV.get_dividend", mock_fmv_get_dividend)

    # Patch the get_fundamentals method on the FMV class
    monkeypatch.setattr("espp2.fmv.FMV.get_fundamentals", mock_fmv_get_fundamentals)

    trans1901 = load_transactions(
        "aksjonaermodellen/EquityAwardsCenter_Transactions-1901.json"
    )
    trans1902 = load_transactions(
        "aksjonaermodellen/EquityAwardsCenter_Transactions-1902.json"
    )
    trans1903 = load_transactions(
        "aksjonaermodellen/EquityAwardsCenter_Transactions-1903.json"
    )
    trans1904 = load_transactions(
        "aksjonaermodellen/EquityAwardsCenter_Transactions-1904.json"
    )

    # Generate holdings for 1901
    rep1901, hold1901, _, sum1901 = tax_report(
        1901,
        "schwab",
        trans1901,
        None,
        None,
        portfolio_engine=True,
    )
    assert hold1901.stocks[0].symbol == "SEAM"
    assert hold1901.stocks[0].qty == 100
    assert hold1901.stocks[0].tax_deduction == 0

    # Generate holdings for 1902
    rep1902, hold1902, _, sum1902 = tax_report(
        1902,
        "schwab",
        trans1902,
        None,
        hold1901,
        portfolio_engine=True,
    )
    assert hold1902.stocks[0].symbol == "SEAM"
    assert hold1902.stocks[0].qty == 100
    assert hold1902.stocks[0].tax_deduction == Decimal("1.5")  # 0.5 * 10 * 0.3

    # Generate holdings for 1903
    rep1903, hold1903, _, sum1903 = tax_report(
        1903,
        "schwab",
        trans1903,
        None,
        hold1902,
        portfolio_engine=True,
    )
    assert hold1903.stocks[0].symbol == "SEAM"
    assert hold1903.stocks[0].qty == 100
    assert hold1903.stocks[0].tax_deduction == Decimal("3.0375")

    # print("RESULT", hold1903)

    # Generate holdings for 1904
    rep1904, hold1904, _, sum1904 = tax_report(
        1904,
        "schwab",
        trans1904,
        None,
        hold1903,
        portfolio_engine=True,
    )
    print("RESULT", sum1904)
    assert sum1904.foreignshares[0].taxable_gain == Decimal("1696.00")
    assert sum1904.foreignshares[0].tax_deduction_used == Decimal("3.04") * 100
