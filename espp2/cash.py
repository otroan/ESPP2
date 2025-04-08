import logging
from copy import deepcopy
from math import isclose

# pylint: disable=logging-fstring-interpolation
from datetime import datetime
from decimal import Decimal
from espp2.fmv import FMV
from espp2.datamodels import (
    CashModel,
    CashEntry,
    Amount,
    TransferRecord,
    CashSummary,
    WireAmount,
    EOYBalanceComparison,
    TransferType,
)

logger = logging.getLogger(__name__)

f = FMV()


class CashException(Exception):
    """Cash exception"""


class Cash:
    """Cash balance"""

    def __init__(
        self,
        year,
        opening_balance=[],
        generate_holdings=False,
        user_input_cash_balance: EOYBalanceComparison = None,
    ):
        """Initialize cash balance for a given year."""
        self.year = year
        self.cash = CashModel().cash
        self.generate_holdings = generate_holdings
        self.user_input_cash_balance = user_input_cash_balance

        # Spin through and add the opening balance
        for e in opening_balance:
            self.cash.append(e)

        self.cash_adjustments()

    def cash_adjustments(self):
        ledger = self.ledger()
        amountdate = datetime(self.year - 1, 12, 31)
        if self.user_input_cash_balance is not None:
            current_balance = ledger[-1][1] if ledger else Decimal("0")
            cash_diff = self.user_input_cash_balance.cash_qty - current_balance

            if abs(cash_diff) > Decimal("10"):
                logger.error(
                    f"Cash quantity mismatch exceeds 10 USD for year {self.year - 1}: "
                    f"expected {current_balance}, got {self.user_input_cash_balance.cash_qty}. "
                    f"Difference: {abs(cash_diff)}."
                )
                return

            if cash_diff > 0:
                logger.warning(
                    f"Minor cash mismatch detected for year {self.year - 1}: "
                    f"expected {current_balance}, got {self.user_input_cash_balance.cash_qty}. "
                    f"Difference: {cash_diff}."
                )
                self.debit(
                    amountdate,
                    Amount(currency="USD", value=cash_diff, amountdate=amountdate),
                    "cash balance adjustment (debit)",
                )
            elif cash_diff < 0:
                logger.warning(
                    f"Minor cash mismatch detected for year {self.year - 1}: "
                    f"expected {current_balance}, got {self.user_input_cash_balance.cash_qty}. "
                    f"Difference: {cash_diff}."
                )
                self.credit(
                    amountdate,
                    Amount(currency="USD", value=cash_diff, amountdate=amountdate),
                    "cash balance adjustment (credit)",
                )

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

    def credit(
        self,
        creditdate,
        amount,
        description="",
        transfer: TransferType = TransferType.NO,
    ):
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
                self.credit(match.date, amount, "wire", transfer=TransferType.YES)
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
                self.credit(w.date, w.amount, "wire", transfer=TransferType.UNMATCHED)
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
        self, entry_index, sale_date, sale_price_nok, gain_nok
    ) -> bool:
        """Update sale information for a cash entry at the given index.

        Args:
            entry_index (int): Index of the entry in self.cash to update
            sale_date (datetime): Date when the sale occurred
            sale_price_nok (float): Sale price in NOK.
            For dividends the gain is subtracted source tax.
        """
        self.cash[entry_index].sale_date = sale_date
        self.cash[entry_index].sale_price_nok = sale_price_nok
        delta = sale_date - self.cash[entry_index].date
        self.cash[entry_index].aggregated = (
            True
            if delta.days <= 14 and self.cash[entry_index].description == "sale"
            else False
        )
        self.cash[entry_index].gain_nok = gain_nok
        return self.cash[entry_index].aggregated

    def process_dividend_taxes(self, cash_positions):
        """Process dividend taxes by matching dividend entries with their tax records"""
        # Find all dividend entries and tax entries
        dividends = [e for e in cash_positions if e.description == "dividend"]
        taxes = [e for e in cash_positions if e.description == "tax"]

        # For each dividend, find and subtract matching tax
        for div in dividends:
            # Find tax entries on same date for same amount
            matching_taxes = [
                t
                for t in taxes
                if t.date == div.date and abs(t.amount.value) <= abs(div.amount.value)
            ]

            # Subtract tax amount from dividend
            for tax in matching_taxes:
                div.amount += tax.amount

                # Mark tax as processed
                tax.amount.value = 0

        return cash_positions

    def process(self):  # noqa: C901
        """Process cash account"""
        cash_positions = deepcopy(self.cash)

        cash_positions = self.process_dividend_taxes(cash_positions)

        # Store original fee NOK values (negative) by date
        original_fee_nok_map = {
            entry.date: entry.amount.nok_value
            for entry in self.cash
            if entry.description == "wire fee"
        }

        posidx = 0
        debit = [e for e in cash_positions if e.amount.value > 0]
        # Get all potential credit entries from the copy first
        all_credit_entries_in_copy = [e for e in cash_positions if e.amount.value < 0]
        # Identify original indices of all potential credit entries
        original_credit_indices = [
            i for i, entry in enumerate(self.cash) if entry.amount.value < 0
        ]
        # Map index in copied list to index in original list
        credit_copy_to_original = {
            i: original_credit_indices[i]
            for i in range(len(all_credit_entries_in_copy))
        }

        transfers = []

        # Create a mapping of original entries to their copies using indices
        original_debit_indices = [
            i for i, e in enumerate(self.cash) if e.amount.value > 0
        ]
        copy_to_original = {i: original_debit_indices[i] for i in range(len(debit))}

        # Iterate through the *filtered* list for FIFO processing
        # We need the index relative to the *original* all_credit_entries_in_copy list to use the map
        # This is getting complicated. Let's iterate all credits and skip FIFO for fees.

        # Revert: Iterate through ALL credits from the copy
        for copy_idx, e in enumerate(all_credit_entries_in_copy):
            logger.debug("\n--- Processing Credit Entry ---")
            logger.debug(
                f"Credit Date: {e.date}, Amount: {e.amount}, Rate (NOK): {e.amount.nok_exchange_rate}, Transfer: {e.transfer}"
            )

            if e.description == "wire fee":
                original_fee_idx = credit_copy_to_original[copy_idx]
                # Use update_sale_info to mark the fee. Sale date is fee date, price and gain are the fee amount.
                self.update_sale_info(
                    entry_index=original_fee_idx,
                    sale_date=e.date,
                    sale_price_nok=e.amount.nok_value,
                    gain_nok=e.amount.nok_value,
                )

            total_received_price_nok = 0
            total_paid_price_nok = 0
            total_gain = 0
            total_gain_aggregated = 0
            amount_to_sell = abs(e.amount.value)
            is_transfer = e.transfer != TransferType.NO
            if is_transfer:
                total_received_price_nok += abs(e.amount.nok_value)
                logger.debug(
                    "  Initial total_received_price_nok: %s", total_received_price_nok
                )

            while amount_to_sell > 0 and posidx < len(debit):
                current_debit = debit[posidx]
                logger.debug("  -- Checking Debit Entry %s --", posidx)
                logger.debug(
                    "  Debit Date: %s, Amount: %s, Rate (NOK): %s, Orig NOK Value: %s %s",
                    current_debit.date,
                    current_debit.amount,
                    current_debit.amount.nok_exchange_rate,
                    current_debit.amount.nok_value,
                    current_debit.description,
                )

                original_debit_value = (
                    current_debit.amount.value
                )  # Store original value before potential modification
                original_debit_nok_value = (
                    current_debit.amount.nok_value
                )  # Store original nok_value

                logger.debug(
                    "  Amount needed: %s, Amount available: %s",
                    amount_to_sell,
                    original_debit_value,
                )
                # amount = debit[posidx].amount.value # Use original_debit_value instead
                logger.debug("Amount: %s", original_debit_value)
                if original_debit_value == 0:
                    logger.debug("  Skipping debit %s with zero amount.", posidx)
                    posidx += 1
                    continue
                if amount_to_sell >= original_debit_value:
                    logger.debug("  Using full debit entry %s.", posidx)
                    amount_used = original_debit_value  # Amount used from this debit
                    if is_transfer:
                        # Determine the NOK cost basis for the amount used (full debit)
                        cost_basis_nok = original_debit_nok_value

                        # Determine the sale value NOK: cost basis for unmatched, calculated for matched
                        if e.transfer == TransferType.UNMATCHED:
                            sale_value_nok = (
                                cost_basis_nok  # Set sale = cost for unmatched
                            )
                        else:  # Matched transfer
                            sale_value_nok = amount_used * e.amount.nok_exchange_rate

                        # Accumulate total paid (cost basis)
                        total_paid_price_nok += cost_basis_nok

                        # Update the debit entry being processed (copy)
                        debit[posidx].sale_price_nok = sale_value_nok
                        debit[posidx].sale_date = e.date

                        # Calculate gain for this chunk
                        gain_nok = sale_value_nok - cost_basis_nok

                        logger.debug(
                            "    Sale Value (NOK) used for gain calc: %s",
                            sale_value_nok,
                        )
                        logger.debug("    Cost Basis (NOK): %s", cost_basis_nok)
                        logger.debug("    Calculated Gain (Full Debit): %s", gain_nok)

                        # Update the original cash entry and check aggregation
                        aggregated = self.update_sale_info(
                            copy_to_original[posidx],
                            e.date,
                            sale_value_nok,  # Use potentially adjusted sale_value_nok
                            gain_nok,  # Use calculated gain_nok
                        )
                        if aggregated:
                            logger.debug(
                                "    >>> Adding AGGREGATED gain: %.2f (derived from net sale value %.2f, cost basis %.2f)",
                                gain_nok,
                                sale_value_nok,
                                cost_basis_nok,
                            )
                            total_gain_aggregated += gain_nok
                        else:
                            logger.debug(
                                "    >>> Adding NON-AGGREGATED gain: %.2f (derived from net sale value %.2f, cost basis %.2f)",
                                gain_nok,
                                sale_value_nok,
                                cost_basis_nok,
                            )
                            total_gain += gain_nok
                    amount_to_sell -= amount_used  # Use amount_used
                    debit[
                        posidx
                    ].amount.value = 0  # Set value directly, __setattr__ handles cache
                    logger.debug(
                        "    Debit %s amount after setting to 0: %s",
                        posidx,
                        debit[posidx].amount,
                    )
                    assert debit[posidx].amount.nok_value == Decimal(0), (
                        f"NOK value should be 0 after setting value to 0, but is {debit[posidx].amount.nok_value}"
                    )
                    logger.debug("    Amount remaining to sell: %s", amount_to_sell)
                    posidx += 1
                else:
                    logger.debug("  Using partial debit entry %s.", posidx)
                    amount_used = amount_to_sell  # Amount used from this debit is the remaining amount_to_sell
                    if is_transfer:
                        # Determine the proportional NOK cost basis for the partial amount used
                        proportional_cost_basis = original_debit_nok_value * (
                            amount_used / original_debit_value
                        )
                        cost_basis_nok = (
                            proportional_cost_basis  # Use this name for consistency
                        )

                        # Determine the sale value NOK: cost basis for unmatched, calculated for matched
                        if e.transfer == TransferType.UNMATCHED:
                            sale_value_nok = (
                                cost_basis_nok  # Set sale = cost for unmatched
                            )
                        else:  # Matched transfer
                            sale_value_nok = amount_used * e.amount.nok_exchange_rate

                        # Accumulate total paid (cost basis)
                        total_paid_price_nok += cost_basis_nok

                        # Update the debit entry being processed (copy) - partial sale info IS relevant
                        # We record the sale price and date for the portion sold.
                        # Gain/aggregation below relates to the original entry.
                        debit[posidx].sale_price_nok = sale_value_nok
                        debit[posidx].sale_date = e.date

                        # Calculate gain for this chunk
                        gain_nok = sale_value_nok - cost_basis_nok

                        logger.debug(
                            "    Sale Value (NOK) used for gain calc: %s",
                            sale_value_nok,
                        )
                        logger.debug(
                            "    Original Debit Value: %s, Original Debit NOK Value: %s",
                            original_debit_value,
                            original_debit_nok_value,
                        )
                        logger.debug(
                            "    Proportion Used: %s / %s = %s",
                            amount_used,
                            original_debit_value,
                            amount_used / original_debit_value,
                        )
                        logger.debug(
                            "    Proportional Cost Basis (NOK): %s * (%s / %s) = %s",
                            original_debit_nok_value,
                            amount_used,
                            original_debit_value,
                            proportional_cost_basis,
                        )
                        logger.debug(
                            "    Calculated Gain (Partial Debit): %s", gain_nok
                        )

                        # Update the original cash entry and check aggregation
                        aggregated = self.update_sale_info(
                            copy_to_original[posidx],
                            e.date,
                            sale_value_nok,  # Use potentially adjusted sale_value_nok
                            gain_nok,  # Use calculated gain_nok
                        )
                        if aggregated:
                            logger.debug(
                                "    >>> Adding AGGREGATED gain: %.2f (derived from net sale value %.2f, cost basis %.2f)",
                                gain_nok,
                                sale_value_nok,
                                proportional_cost_basis,  # Use proportional cost basis here
                            )
                            total_gain_aggregated += gain_nok
                        else:
                            logger.debug(
                                "    >>> Adding NON-AGGREGATED gain: %.2f (derived from net sale value %.2f, cost basis %.2f)",
                                gain_nok,
                                sale_value_nok,
                                proportional_cost_basis,  # Use proportional cost basis here
                            )
                            total_gain += gain_nok
                    debit[
                        posidx
                    ].amount -= amount_to_sell  # Subtract the amount_used (which equals amount_to_sell here)
                    # debit[posidx].amount.nok_value -= amount_to_sell * e.amount.nok_exchange_rate # This seems incorrect, __sub__ should handle value, but nok_value needs care
                    logger.debug(
                        "    Debit %s amount after subtraction: %s",
                        posidx,
                        debit[posidx].amount,
                    )
                    # Note: Accessing debit[posidx].amount.nok_value here might recalculate based on the *new* value, which could be wrong for remaining cost basis tracking.
                    amount_to_sell = 0
            if amount_to_sell > 0:
                logger.error(
                    f"Transferring more money than is in cash account {amount_to_sell} {e}"
                )

            # Create TransferRecord if applicable
            if e.transfer != TransferType.NO:
                # Lookup fee associated with this transfer date
                # fee_nok will be negative as it's a cost
                fee_nok = original_fee_nok_map.get(e.date, Decimal(0))
                logger.debug("  Fee found for date %s: %.2f", e.date, fee_nok)

                if total_gain_aggregated != 0:
                    # If there's agg gain, apply the whole fee there
                    total_gain_aggregated += fee_nok  # fee_nok is negative
                    logger.debug(
                        "  Adjusting Aggregated Gain: %.2f + (%.2f) = %.2f",
                        total_gain_aggregated
                        - fee_nok,  # Original value before adding fee
                        fee_nok,
                        total_gain_aggregated,
                    )
                else:
                    # Otherwise, apply fee to non-aggregated gain
                    total_gain += fee_nok  # fee_nok is negative
                    logger.debug(
                        "  Adjusting Non-Aggregated Gain: %.2f + (%.2f) = %.2f",
                        total_gain - fee_nok,  # Original value before adding fee
                        fee_nok,
                        total_gain,
                    )
                if e.transfer == TransferType.UNMATCHED:
                    amount_received = total_paid_price_nok
                    gain = 0
                    aggregated_gain = 0
                else:
                    amount_received = total_received_price_nok
                    gain = total_gain
                    aggregated_gain = total_gain_aggregated
                transfers.append(
                    TransferRecord(
                        date=e.date,
                        amount_sent=round(total_paid_price_nok),
                        amount_received=round(amount_received),
                        description=e.description,
                        gain=round(gain),
                        aggregated_gain=round(aggregated_gain),
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
