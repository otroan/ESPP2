import pytest

import espp2.plugins.td as td
from espp2.datamodels import Transactions

def test_td_import():
    with open('test/td.csv', 'r', encoding='utf-8') as f:
        t = td.read(f)
    assert isinstance(t, Transactions)