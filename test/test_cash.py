from espp2.positions import Cash
from espp2.datamodels import Amount, Wire, EntryTypeEnum, Transactions


def test_cash():
    # Test cash
    return
    w = Wire(
        type=EntryTypeEnum.WIRE,
        date="2022-10-26",
        amount=Amount(
            currency="USD", value=-1000, nok_value=-10000, nok_exchange_rate=9
        ),
        fee=Amount(currency="USD", value=-15, nok_value=-150, nok_exchange_rate=9),
        description="Wire from bank",
        source="test",
    )
    t = Transactions(transactions=[w])

    c = Cash(2022, t.transactions)
    # c.credit('2022-10-26', Amount(currency='USD', value=-1000, nok_value=-10000, nok_exchange_rate=10), transfer=True)

    c.debit(
        "2022-01-01",
        Amount(currency="USD", value=100, nok_value=1000, nok_exchange_rate=10),
    )
    c.debit(
        "2022-01-25",
        Amount(currency="USD", value=1000, nok_value=10000, nok_exchange_rate=11),
    )
    # print('cash', c.cash)
    c.credit(
        "2022-11-26",
        Amount(currency="USD", value=-10, nok_value=-1000, nok_exchange_rate=11),
        transfer=True,
    )
    # c.credit('2022-11-26', Amount(currency='USD', value=-10,
    #          nok_value=-1000, nok_exchange_rate=10), transfer=True)
    # c.credit('2022-11-26', Amount(currency='USD', value=-10,
    #          nok_value=-1000, nok_exchange_rate=10), transfer=True)
    # c.credit('2022-11-26', Amount(currency='USD', value=-1000,
    #          nok_value=-10000, nok_exchange_rate=10), transfer=True)

    # nomatch = c.wire(t.transactions, None)
    ledger = c.ledger()
    print()
    for i in ledger:
        print("LEDGER:", str(i[0].date), i[1])

    summary = c.process()
    print("TAX SUMMARY", summary)


def test_cash_from_previous_year():
    assert 1 == 1
