
import espp2.plugins.schwab as schwab
from espp2.datamodels import Transactions


def test_schwab_import():
    with open("test/schwab.csv", "r", encoding="utf-8") as f:
        t = schwab.read(f)
    assert isinstance(t, Transactions)
