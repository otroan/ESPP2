import logging
from copy import deepcopy
from math import isclose
from datetime import datetime
from espp2.fmv import FMV
from espp2.datamodels import (
    CashModel,
    CashEntry,
    Amount,
    TransferRecord,
    CashSummary,
    WireAmount,
)

logger = logging.getLogger(__name__)

f = FMV()


class CashException(Exception):
    """Cash exception"""


class Cash:
    """Cash balance"""

    def __init__(self, year, opening_balance=[], generate_holdings=False):
        """Initialize cash balance for a given year."""
        self.year = year
        self.cash = CashModel().cash
        self.generate_holdings = generate_holdings

        # Spin through and add the opening balance
        for e in opening_balance:
            self.cash.append(e)

    def sort(self):
        """Sort cash entries by date"""
        self.cash = sorted(self.cash, key=lambda d: d.date)

    def debit(self, debitdate, amount, description=""):
        """Debit cash balance"""
        logger.debug("Cash debit: %s: %s", debitdate, amount.value)
        if amount.value < 0:
            raise ValueError("Amount must be positive")
        self.cash.append(
            CashEntry(date=debitdate, amount=amount, description=description)
        )
        self.sort()

    def credit(self, creditdate, amount, description="", transfer=False):
        """TODO: Return usdnok rate for the item credited"""
        logger.debug("Cash credit: %s: %s", creditdate, amount.value)
        if amount.value > 0:
            raise ValueError(f"Amount must be negative {amount}")

        self.cash.append(
            CashEntry(
                date=creditdate,
                amount=amount,
                description=description,
                transfer=transfer,
            )
        )
        self.sort()

    def _wire_match(self, wire, wires_received):
        """Match wire transfer to received record"""
        if isinstance(wires_received, list) and len(wires_received) == 0:
            return None
        try:
            for v in wires_received:
                if v.date == wire.date and isclose(
                    v.value, abs(wire.amount.value), abs_tol=0.05
                ):
                    return v
        except AttributeError as e:
            logger.error(f"No received wires processing failed {wire}")
            raise ValueError(f"No received wires processing failed {wire}") from e
        return None

    def ledger(self):
        """Cash ledger"""
        total = 0
        ledger = []
        for c in self.cash:
            total += c.amount.value
            ledger.append((c, total))
        return ledger

    def wire(self, wire_transactions, wires_received):
        """Process wires from sent and received (manual) records"""
        unmatched = []
        for w in wire_transactions:
            match = self._wire_match(w, wires_received)
            if match:
                amount = Amount(
                    currency=match.currency,
                    value=-1 * match.value,
                    nok_exchange_rate=match.nok_value / match.value,
                )
                self.credit(match.date, amount, "wire", transfer=True)
            else:
                # TODO: What's the exchange rate here?
                # Should be NaN?
                unmatched.append(
                    WireAmount(
                        date=w.date,
                        currency=w.amount.currency,
                        nok_value=w.amount.nok_value,
                        value=w.amount.value,
                    )
                )
                self.credit(w.date, w.amount, "wire", transfer=True)
            if w.fee:
                self.credit(w.date, w.fee, "wire fee")

        if unmatched:
            warning_msg = "Wire Transfers missing corresponding received records:"
            for wire in unmatched:
                exchange_rate = wire.nok_value / wire.value if wire.value != 0 else 0
                warning_msg += f"\n  - {wire.date.strftime('%Y-%m-%d')}: {abs(wire.value):>10.2f} USD / {abs(wire.nok_value):>12.2f} NOK @ {abs(exchange_rate):>6.4f}"
            logger.warning(warning_msg)
        return unmatched

    def update_sale_info(
        self, entry_index, sale_date, sale_price_nok
    ) -> tuple[int, bool]:
        """Update sale information for a cash entry at the given index.

        Args:
            entry_index (int): Index of the entry in self.cash to update
            sale_date (datetime): Date when the sale occurred
            sale_price_nok (float): Sale price in NOK
        """
        self.cash[entry_index].sale_date = sale_date
        self.cash[entry_index].sale_price_nok = sale_price_nok
        delta = sale_date - self.cash[entry_index].date
        self.cash[entry_index].aggregated = True if delta.days <= 14 else False
        self.cash[entry_index].gain_nok = (
            sale_price_nok - self.cash[entry_index].amount.nok_value
        )
        return self.cash[entry_index].gain_nok, self.cash[entry_index].aggregated

    def process(self):  # noqa: C901
        """Process cash account"""
        cash_positions = deepcopy(self.cash)
        posidx = 0
        debit = [e for e in cash_positions if e.amount.value > 0]
        credit = [e for e in cash_positions if e.amount.value < 0]
        transfers = []

        # Create a mapping of original entries to their copies using indices
        original_debit_indices = [
            i for i, e in enumerate(self.cash) if e.amount.value > 0
        ]
        copy_to_original = {i: original_debit_indices[i] for i in range(len(debit))}

        for e in credit:
            total_received_price_nok = 0
            total_paid_price_nok = 0
            total_gain = 0
            total_gain_aggregated = 0
            amount_to_sell = abs(e.amount.value)
            is_transfer = e.transfer
            if is_transfer:
                total_received_price_nok += abs(e.amount.nok_value)
            while amount_to_sell > 0 and posidx < len(debit):
                amount = debit[posidx].amount.value
                if amount == 0:
                    posidx += 1
                    continue
                if amount_to_sell >= amount:
                    if is_transfer:
                        total_paid_price_nok += debit[posidx].amount.nok_value
                        # Update both copy and original entry
                        debit[posidx].sale_price_nok = (
                            amount * e.amount.nok_exchange_rate
                        )
                        debit[posidx].sale_date = e.date
                        gain_nok, aggregated = self.update_sale_info(
                            copy_to_original[posidx],
                            e.date,
                            amount * e.amount.nok_exchange_rate,
                        )
                        if aggregated:
                            total_gain_aggregated += gain_nok
                        else:
                            total_gain += gain_nok
                    amount_to_sell -= amount
                    debit[posidx].amount.value = 0
                    posidx += 1
                else:
                    if is_transfer:
                        total_paid_price_nok += (
                            amount_to_sell * debit[posidx].amount.nok_exchange_rate
                        )
                        # Update both copy and original entry
                        debit[posidx].sale_price_nok = (
                            amount_to_sell * e.amount.nok_exchange_rate
                        )
                        debit[posidx].sale_date = e.date
                        gain_nok, aggregated = self.update_sale_info(
                            copy_to_original[posidx],
                            e.date,
                            amount_to_sell * e.amount.nok_exchange_rate,
                        )
                        if aggregated:
                            total_gain_aggregated += gain_nok
                        else:
                            total_gain += gain_nok
                    debit[posidx].amount.value -= amount_to_sell
                    amount_to_sell = 0
            if amount_to_sell > 0:
                logger.error(
                    f"Transferring more money than is in cash account {amount_to_sell} {e}"
                )

            # Only care about tranfers
            if is_transfer:
                transfers.append(
                    TransferRecord(
                        date=e.date,
                        amount_sent=round(total_paid_price_nok),
                        amount_received=round(total_received_price_nok),
                        description=e.description,
                        gain=round(total_gain),
                        aggregated_gain=round(total_gain_aggregated),
                    )
                )
        remaining_usd = sum([c.amount.value for c in debit if c.amount.value > 0])
        eoy = datetime(self.year, 12, 31)
        remaining_cash = Amount(
            value=remaining_usd,
            currency="USD",
            amountdate=eoy,
        )
        total_gain = sum([t.gain for t in transfers])
        total_gain_aggregated = sum([t.aggregated_gain for t in transfers])
        total_paid_price_nok = sum([t.amount_sent for t in transfers])
        total_received_price_nok = sum([t.amount_received for t in transfers])

        # Cash holdings. List of WireAmounts
        cash_holdings = []
        for e in debit:
            if e.amount.value > 0:
                cash_holdings.append(
                    CashEntry(date=e.date, description=e.description, amount=e.amount)
                )
        return CashSummary(
            transfers=transfers,
            remaining_cash=remaining_cash,
            gain=total_gain,
            gain_aggregated=total_gain_aggregated,
            holdings=cash_holdings,
        )
