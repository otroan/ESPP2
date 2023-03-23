

import espp2.plugins.csco_espp_purchases as csco_espp_purchases
import espp2.plugins.csco_espp_transactions as csco_espp_transactions
import espp2.plugins.csco_stock_transactions as csco_stock_transactions
from espp2.datamodels import Transactions
from espp2.positions import Ledger
from espp2.report import print_ledger
from rich.console import Console

def test_cisco_import():
    trans = []
    with open('test/My_ESPP_Purchases.xlsx', 'rb') as f:
        t = csco_espp_purchases.read(f)
    assert isinstance(t, Transactions)
    trans += t.transactions
    with open('test/My_ESPP_Transactions.xlsx', 'rb') as f:
        t = csco_espp_transactions.read(f)
    assert isinstance(t, Transactions)
    trans += t.transactions

    with open('test/My_Stock_Transactions.xlsx', 'rb') as f:
        t = csco_stock_transactions.read(f)
    assert isinstance(t, Transactions)
    trans += t.transactions

    all = Transactions(transactions=trans)

    ledger = Ledger([], all.transactions)
    console = Console()
    print_ledger(ledger.entries, console)
