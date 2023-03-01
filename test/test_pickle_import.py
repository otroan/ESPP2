import pytest

import espp2.plugins.pickle as pickle
from espp2.datamodels import Transactions

def test_pickle_import():
    with open('test/espp.pickle', 'rb') as f:
        t = pickle.read(f)
    assert isinstance(t, Transactions)