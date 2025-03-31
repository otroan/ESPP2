import json
import os
import re
import pytest

from datetime import datetime, date
from decimal import Decimal
from typer.testing import CliRunner

from espp2.main import tax_report, do_holdings
from espp2.datamodels import (
    Transactions,
    Holdings,
    ForeignShares,
    CreditDeduction,
    TransferRecord,
    Amount,
    CashEntry,
    CashSummary,
    TaxSummary,
    Stock,
)
from espp2.transactions import plugin_read
from espp2.espp2 import app

runner = CliRunner()

# Test files:
# test/schwab1.json:
#   - Complete transactions from 2023 until 2025
#     Requires first to generate holdings for 2023, then tax generation for 2024


def test_full_run(tmp_path):
    holdings_2023 = tmp_path / "holdings-2023.json"

    base_dir = os.path.dirname(__file__)
    holdings = os.path.join(base_dir, "schwab1.json")

    # Run for 2023 to generate outholdings
    result = runner.invoke(
        app,
        [
            holdings,
            "--verbose",
            "--year=2023",
            "--outholdings",
            holdings_2023,
        ],
    )
    print("RESULT", result.stdout)
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            holdings,
            "--verbose",
            "--year=2024",
            "--inholdings",
            holdings_2023,
        ],
    )
    print("RESULT", result.stdout)
    assert result.exit_code == 0


def test_stock1(tmp_path):
    base_dir = os.path.dirname(__file__)
    transfile = os.path.join(base_dir, "schwab1.json")

    with open(transfile, "r", encoding="utf-8") as f:
        transactions = plugin_read(f, transfile, "schwab-json")

    # Generate holdings for 2023
    report2023, holdings2023, exceldata2023, summary2023 = tax_report(
        2023,
        "schwab",
        transactions,
        None,
        None,
        portfolio_engine=True,
        verbose=True,
        feature_flags=[],
    )
    assert holdings2023.stocks[0].symbol == "CSCO"
    assert holdings2023.stocks[0].qty == 41

    # Generate tax report for 2024
    report2024, holdings2024, exceldata2024, summary2024 = tax_report(
        2024,
        "schwab",
        transactions,
        None,
        holdings2023,
        portfolio_engine=True,
        verbose=True,
        feature_flags=[],
    )
    assert holdings2024.stocks[0].symbol == "CSCO"
    assert holdings2024.sum_qty() == 103


def test_holdings_consistency_between_generated_and_actual_holdings_for_entire_history():
    previous_year = datetime.now().year - 1
    previous_tax_year = previous_year - 1
    two_tax_years_ago = previous_tax_year - 1

    holdings_file = f"espp-holdings-{previous_tax_year}.json"
    holdings_file_previous_year = f"espp-holdings-{two_tax_years_ago}.json"

    previous_holdings = generated_holdings_file(holdings_file_previous_year)
    if previous_holdings is None:
        pytest.skip("No previous holdings file found, skipping test")

    transactions = get_transactions_files()[0]

    report_2023, new_holdings, excel_data_2023, summary_2023 = tax_report(
        2023,
        "schwab",
        transactions,
        [],
        previous_holdings,
        portfolio_engine=True,
        verbose=True,
        feature_flags=[],
    )

    actual_holdings = generated_holdings_file(holdings_file)
    assert new_holdings.sum_qty() == actual_holdings.sum_qty()
    assert new_holdings.stocks[0].symbol == actual_holdings.stocks[0].symbol


def test_holdings_consistency_between_generated_holdings_and_previous_year_transaction_file(
    snapshot,
):
    base_dir = os.path.dirname(__file__)
    previous_holdings_file = os.path.join(
        base_dir, "testfiles/user2/holdings-2023.json"
    )
    transactions_file = os.path.join(
        base_dir, "testfiles/user2/EquityAwardsCenter_Transactions_20250212213044.json"
    )

    previous_holdings = generated_holdings_file(previous_holdings_file)
    transactions = get_transactions_files([transactions_file])

    report_2024, new_holdings, excel_data_2024, summary_2024 = tax_report(
        2024,
        "schwab",
        transactions[0],
        [],
        previous_holdings,
        portfolio_engine=True,
        verbose=True,
        feature_flags=[],
    )

    snapshot_data = {
        "eoy_balance_symbol": report_2024.eoy_balance[2024][0].symbol,
        "eoy_balance_qty": str(report_2024.eoy_balance[2024][0].qty),
        "summary": serialize_object(summary_2024),
        "new_holdings": serialize_object(new_holdings),
    }
    snapshot.assert_match(
        json.dumps(snapshot_data, indent=4), "tax_report_2024_snapshot"
    )


def test_holdings_consistency_for_all_users(snapshot):
    base_dir = os.path.dirname(__file__)
    testfiles_dir = os.path.join(base_dir, "testfiles")

    for user_folder in os.listdir(testfiles_dir):
        user_path = os.path.join(testfiles_dir, user_folder)
        if not os.path.isdir(user_path):
            continue

        holdings_file = os.path.join(user_path, "espp-holdings-2023.json")
        if not holdings_file:
            continue

        transactions_files = [
            os.path.join(user_path, f)
            for f in os.listdir(user_path)
            if f.startswith("EquityAwardsCenter_Transactions_") and f.endswith(".json")
        ]

        if not os.path.exists(holdings_file) or not transactions_files:
            continue

        previous_holdings = generated_holdings_file(holdings_file)
        if previous_holdings is None:
            pytest.skip(f"No valid holdings file found in {user_folder}, skipping test")
        transactions_list = get_transactions_files(transactions_files)

        # Generate holdings and tax report
        holdings = do_holdings(
            "schwab",
            transactions_list,
            2024,
            verbose=True,
        )

        report2023, holdings2023, exceldata2023, summary2023 = tax_report(
            2024,
            "schwab",
            transactions_list[-1],
            [],
            holdings,
            portfolio_engine=True,
            verbose=True,
            feature_flags=[],
        )

        snapshot_data = {
            "user_folder": user_folder,
            "holdings2023_sum_qty": holdings2023.sum_qty(),
            "holdings2023_first_stock_symbol": holdings2023.stocks[0].symbol
            if holdings2023.stocks
            else None,
        }
        snapshot.assert_match(
            json.dumps(snapshot_data, indent=4),
            f"holdings_consistency_snapshot_{user_folder}",
        )


def generated_holdings_file(filename: str) -> Holdings:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            new_holdings_data = json.load(f)
    except FileNotFoundError:
        return None

    return Holdings(
        year=new_holdings_data["year"],
        broker=new_holdings_data["broker"],
        stocks=new_holdings_data["stocks"],
        cash=new_holdings_data["cash"],
    )


def get_transactions_files(files: list = None) -> list[Transactions]:
    transactions_files = []
    if files is None:
        return []

    pattern = r"EquityAwardsCenter_Transactions_.*\.json"
    for filename in files:
        if re.search(pattern, filename):
            transactions_files.append(filename)

    transactions_list = []
    for transactions_file in transactions_files:
        with open(transactions_file, "r", encoding="utf-8") as f:
            transactions = plugin_read(f, transactions_file, "schwab-json")
            transactions_list.append(transactions)

    return transactions_list


def serialize_object(obj):
    if isinstance(
        obj,
        (
            ForeignShares,
            CreditDeduction,
            TransferRecord,
            Amount,
            CashEntry,
            CashSummary,
            TaxSummary,
            Holdings,
            Stock,
        ),
    ):
        return {k: serialize_object(v) for k, v in vars(obj).items()}
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, list):
        return [serialize_object(item) for item in obj]
    return obj
