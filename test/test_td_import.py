import pytest

import espp2.plugins.td as td
from espp2.datamodels import Transactions


def test_td_import():
    with open("test/td.csv", "r", encoding="utf-8") as f:
        with pytest.raises(Exception) as e_info:  # noqa: F841
            t = td.read(f)
            assert isinstance(t, Transactions)


def test_td_import_fixed():
    with open("test/td2.csv", "r", encoding="utf-8") as f:
        t = td.read(f)
        assert isinstance(t, Transactions)
