from espp2.datamodels import (
    Transactions,
    Dividend,
    EntryTypeEnum,
    Amount,
    PositiveAmount,
    Deposit,
    Wire,
)
from espp2.portfolio import Portfolio
import logging
import datetime


def test_dividends(caplog):
    caplog.set_level(logging.INFO)
    # Create a dividend object
    transactions = []

    transactions.append(
        Deposit(
            type=EntryTypeEnum.DEPOSIT,
            date="2022-08-26",
            symbol="CSCO",
            qty=100,
            purchase_date="2022-10-26",
            purchase_price=Amount(currency="USD", value=10, amountdate="2022-10-26"),
            description="",
            source="test",
        )
    )
    transactions.append(
        Deposit(
            type=EntryTypeEnum.DEPOSIT,
            date="2022-10-10",
            symbol="CSCO",
            qty=100,
            purchase_date="2022-10-26",
            purchase_price=Amount(currency="USD", value=10, amountdate="2022-10-26"),
            description="",
            source="test",
        )
    )

    d = Dividend(
        type=EntryTypeEnum.DIVIDEND,
        date="2022-10-26",
        symbol="CSCO",
        amount=PositiveAmount(currency="USD", value=38, amountdate="2022-10-26"),
        source="test",
    )
    assert d.exdate == datetime.date(2022, 10, 4)
    transactions.append(d)

    t = Transactions(transactions=transactions)
    # c = Cash(2022, t.transactions, None)
    p = Portfolio(2022, "schwab", t.transactions, None, None, False, [])
    dividends = p.dividends()
    assert dividends[0].symbol == "CSCO"
    assert dividends[0].amount.usd_value == 38
    for record in caplog.records:
        if record.funcName == "dividends":
            assert (
                record.message
                == "Total shares of CSCO at dividend date: 100 dps: 0.38 reported: 0.38"
            )


def test_wire():
    w = Wire(
        type=EntryTypeEnum.WIRE,
        date="2022-11-25",
        amount=Amount(
            currency="USD", value=-24535.66, nok_value=-243548, nok_exchange_rate=9.9263
        ),
        source="test",
        description="Cash Disbursement",
    )

    assert w.fee is None
