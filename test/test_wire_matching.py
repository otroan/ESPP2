from decimal import Decimal
from datetime import date
from espp2.datamodels import TransferRecord, WireAmount
from espp2.portfolio import generate_wires_from_transactions


def test_multiple_wires_same_date():
    """Test matching multiple wire transactions on the same date"""

    # Create unmatched wire amounts
    unmatched_wires = [
        WireAmount(
            date=date(2024, 7, 20),
            currency="USD",
            value=Decimal("1000"),
            nok_value=Decimal("0"),  # Will be updated by the function
        ),
        WireAmount(
            date=date(2024, 7, 20),
            currency="USD",
            value=Decimal("2000"),
            nok_value=Decimal("0"),  # Will be updated by the function
        ),
    ]

    # Create TransferRecord objects that would be generated from the cash processing
    transfer_records = [
        TransferRecord(
            date=date(2024, 7, 20),
            amount_sent=Decimal("1000"),
            amount_received=Decimal("10000"),
            gain=Decimal("0"),
            aggregated_gain=Decimal("0"),
            description="wire",
        ),
        TransferRecord(
            date=date(2024, 7, 20),
            amount_sent=Decimal("2000"),
            amount_received=Decimal("20000"),
            gain=Decimal("0"),
            aggregated_gain=Decimal("0"),
            description="wire",
        ),
    ]

    # Call the function
    result = generate_wires_from_transactions(transfer_records, unmatched_wires)

    # Verify that both wires were matched and have NOK values set
    assert len(result) == 2

    # Verify the NOK values were set correctly
    nok_values = sorted([w.nok_value for w in result])
    assert nok_values == [Decimal("10000"), Decimal("20000")]

    # Verify that the wires were matched correctly by amount
    matched_values = sorted([w.value for w in result])
    assert matched_values == [Decimal("1000"), Decimal("2000")]


def test_wire_matching_by_amount():
    """Test that wires are matched by amount when multiple wires exist on the same date"""

    # Create TransferRecord objects with the same date but different amounts
    transfer_records = [
        TransferRecord(
            date=date(2024, 7, 20),
            amount_sent=Decimal("1000"),
            amount_received=Decimal("10000"),
            gain=Decimal("0"),
            aggregated_gain=Decimal("0"),
            description="wire",
        ),
        TransferRecord(
            date=date(2024, 7, 20),
            amount_sent=Decimal("2000"),
            amount_received=Decimal("20000"),
            gain=Decimal("0"),
            aggregated_gain=Decimal("0"),
            description="wire",
        ),
    ]

    # Create unmatched wire amounts in reverse order to test matching by amount
    unmatched_wires = [
        WireAmount(
            date=date(2024, 7, 20),
            currency="USD",
            value=Decimal("2000"),  # This should match the second transfer record
            nok_value=Decimal("0"),  # Will be updated by the function
        ),
        WireAmount(
            date=date(2024, 7, 20),
            currency="USD",
            value=Decimal("1000"),  # This should match the first transfer record
            nok_value=Decimal("0"),  # Will be updated by the function
        ),
    ]

    # Call the function
    result = generate_wires_from_transactions(transfer_records, unmatched_wires)

    # Verify that both wires were matched and have NOK values set
    assert len(result) == 2

    # The first wire (value 2000) should be matched with the second transfer record
    assert result[0].value == Decimal("2000")
    assert result[0].nok_value == Decimal("20000")

    # The second wire (value 1000) should be matched with the first transfer record
    assert result[1].value == Decimal("1000")
    assert result[1].nok_value == Decimal("10000")
