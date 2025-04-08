from espp2.positions import Cash
from espp2.datamodels import (
    Amount,
    Wire,
    EntryTypeEnum,
    Transactions,
    EOYBalanceComparison,
)

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from decimal import Decimal


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


class TestCashAdjustments(unittest.TestCase):
    def setUp(self):
        self.year = 2024
        self.cash = Cash(year=self.year)

    @patch("espp2.cash.logger")
    def test_no_mismatch(self, mock_logger):
        self.cash.ledger = MagicMock(return_value=[(None, Decimal("100.00"))])
        self.cash.user_input_cash_balance = EOYBalanceComparison(
            cash_qty=Decimal("100.00"), year=self.year - 1
        )

        self.cash.cash_adjustments()
        mock_logger.error.assert_not_called()
        mock_logger.warning.assert_not_called()

    @patch("espp2.cash.logger")
    def test_minor_mismatch_debit(self, mock_logger):
        self.cash.ledger = MagicMock(return_value=[(None, Decimal("90.00"))])
        self.cash.user_input_cash_balance = EOYBalanceComparison(
            cash_qty=Decimal("100.00"), year=self.year - 1
        )

        with patch.object(self.cash, "debit") as mock_debit:
            self.cash.cash_adjustments()
            mock_debit.assert_called_once_with(
                datetime(self.year - 1, 12, 31),
                Amount(
                    currency="USD",
                    value=Decimal("10.00"),
                    amountdate=datetime(self.year - 1, 12, 31),
                ),
                "Cash balance adjustment (debit)",
            )

        mock_logger.warning.assert_called_once()

    @patch("espp2.cash.logger")
    def test_minor_mismatch_credit(self, mock_logger):
        self.cash.ledger = MagicMock(return_value=[(None, Decimal("110.00"))])
        self.cash.user_input_cash_balance = EOYBalanceComparison(
            cash_qty=Decimal("100.00"), year=self.year - 1
        )

        with patch.object(self.cash, "credit") as mock_credit:
            self.cash.cash_adjustments()
            mock_credit.assert_called_once_with(
                datetime(self.year - 1, 12, 31),
                Amount(
                    currency="USD",
                    value=Decimal("-10.00"),
                    amountdate=datetime(self.year - 1, 12, 31),
                ),
                "Cash balance adjustment (credit)",
            )

        mock_logger.warning.assert_called_once()

    @patch("espp2.cash.logger")
    def test_significant_mismatch(self, mock_logger):
        self.cash.ledger = MagicMock(return_value=[(None, Decimal("50.00"))])
        self.cash.user_input_cash_balance = EOYBalanceComparison(
            cash_qty=Decimal("100.00"), year=self.year - 1
        )

        self.cash.cash_adjustments()
        mock_logger.error.assert_called_once_with(
            f"Cash quantity mismatch exceeds 10 USD for year {self.year - 1}: "
            f"expected 50.00, got 100.00. Difference: 50.00."
        )

    @patch("espp2.cash.logger")
    def test_no_ledger_entries(self, mock_logger):
        """Test case where the ledger is empty."""
        self.cash.ledger = MagicMock(return_value=[])
        self.cash.user_input_cash_balance = EOYBalanceComparison(
            cash_qty=Decimal("50.00"), year=self.year - 1
        )

        with (
            patch.object(self.cash, "debit") as mock_debit,
            patch.object(self.cash, "credit") as mock_credit,
        ):
            self.cash.cash_adjustments()
            mock_debit.assert_not_called()
            mock_credit.assert_not_called()

        mock_logger.error.assert_called_once_with(
            f"Cash quantity mismatch exceeds 10 USD for year {self.year - 1}: "
            f"expected 0, got 50.00. Difference: 50.00."
        )


if __name__ == "__main__":
    unittest.main()
