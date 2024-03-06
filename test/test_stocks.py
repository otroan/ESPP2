import espp2.plugins.csco_espp_purchases as csco_espp_purchases
import espp2.plugins.csco_stock_transactions as csco_stock_transactions
from espp2.datamodels import Transactions
from espp2.positions import Ledger
from espp2.report import print_ledger
from rich.console import Console
from espp2.espp2 import app
from typer.testing import CliRunner


def test_cisco_import():
    trans = []
    with open("test/My_ESPP_Purchases.xlsx", "rb") as f:
        t = csco_espp_purchases.read(f)
    assert isinstance(t, Transactions)
    trans += t.transactions
    # with open('test/My_ESPP_Transactions.xlsx', 'rb') as f:
    #     t = csco_espp_transactions.read(f)
    # assert isinstance(t, Transactions)
    # trans += t.transactions

    with open("test/My_Stock_Transactions.xlsx", "rb") as f:
        t = csco_stock_transactions.read(f)
    assert isinstance(t, Transactions)
    trans += t.transactions

    all = Transactions(transactions=trans)

    ledger = Ledger([], all.transactions)
    console = Console()
    print_ledger(ledger.entries, console)


runner = CliRunner()


def test_full_run(tmp_path):
    outholdings_2021 = tmp_path / "outholdings-2021.json"
    outholdings_2022 = tmp_path / "outholdings-2022.json"

    result = runner.invoke(
        app, ["test/schwab.csv", "test/espp.pickle", "--outholdings", outholdings_2021]
    )
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "test/schwab.csv",
            "--inholdings",
            outholdings_2021,
            "--outholdings",
            outholdings_2022,
        ],
    )
    print('RESULT', result)
    assert result.exit_code == 0


def test_opening_balance():
    opening_balance = """
{
    "stocks": [
        {
            "symbol": "CSCO",
            "date": "2019-12-31",
            "qty": 1885,
            "tax_deduction": 0,
            "purchase_price": {
                "currency": "USD",
                "value": 53.43
            }
        }
    ],
    "cash": [],
    "year": 2019,
    "broker": "schwab"
}
"""

    result = runner.invoke(
        app, ["test/schwab.csv", "--verbose", "--opening-balance", opening_balance]
    )
    assert result.exit_code == 0
