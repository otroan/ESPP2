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
    fixed_date = datetime(2025, 4, 2)
    previous_year = fixed_date.year - 1
    previous_tax_year = previous_year - 1
    two_tax_years_ago = previous_tax_year - 1

    holdings_file = f"espp-holdings-{previous_tax_year}.json"
    holdings_file_previous_year = f"espp-holdings-{two_tax_years_ago}.json"

    previous_holdings = generated_holdings_file(holdings_file_previous_year)
    if previous_holdings is None:
        pytest.skip("No previous holdings file found, skipping test")

    base_dir = os.path.dirname(__file__)
    transactions_files = [
        os.path.join(base_dir, f)
        for f in os.listdir(base_dir)
        if re.match(r"EquityAwardsCenter_Transactions_.*\.json$", f)
    ]
    if not transactions_files:
        pytest.skip(
            "No valid transactions files found in the current directory, skipping test"
        )
    transactions = Transactions(
        transactions=[
            plugin_read(open(file, "r", encoding="utf-8"), file, "schwab-json")
            for file in transactions_files
        ]
    )

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


def xtest_holdings_consistency_between_generated_holdings_and_previous_year_transaction_file(
    snapshot,
):
    base_dir = os.path.dirname(__file__)
    previous_holdings_file = os.path.join(
        base_dir, "testfiles/user2/espp-holdings-2023.json"
    )
    previous_holdings = generated_holdings_file(previous_holdings_file)

    transactions_file_path = os.path.join(
        base_dir, "testfiles/user2/EquityAwardsCenter_Transactions_2024.json"
    )
    with open(transactions_file_path, "r", encoding="utf-8") as f:
        transactions = plugin_read(f, transactions_file_path, "schwab-json")

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
        "holdings2023_year": previous_holdings.year,
        "holdings2023_broker": previous_holdings.broker,
        "holdings2023_stocks": dump_list(previous_holdings.stocks),
        "holdings2023_cash": dump_list(previous_holdings.cash),
        "report2024_eoy_balance": {
            year: dump_list(items) for year, items in report_2024.eoy_balance.items()
        },
        "report2024_ledger": {
            key: dump_list(value) for key, value in report_2024.ledger.items()
        },
        "report2024_dividends": dump_list(report_2024.dividends),
        "report2024_buys": dump_list(report_2024.buys),
        "report2024_sales": {
            key: dump_list(sales_list) for key, sales_list in report_2024.sales.items()
        },
        "report2024_cash_ledger": dump_list(report_2024.cash_ledger),
        "report2024_unmatched_wires": dump_list(report_2024.unmatched_wires),
    }

    serialized_snapshot_data = serialize_snapshot_data(snapshot_data)
    snapshot.assert_match(
        json.dumps(serialized_snapshot_data, indent=4, default=str),
        "holdings_consistency_snapshot_user2",
    )


def xtest_holdings_consistency_for_all_users(snapshot):
    base_dir = os.path.dirname(__file__)
    testfiles_dir = os.path.join(base_dir, "testfiles")

    for user_folder in os.listdir(testfiles_dir):
        user_path = os.path.join(testfiles_dir, user_folder)
        if not os.path.isdir(user_path):
            continue

        holdings_file = os.path.join(user_path, "espp-holdings-2023.json")
        if not os.path.exists(holdings_file):
            pytest.skip(f"No valid holdings file found in {user_folder}, skipping test")

        transactions_files = [
            os.path.join(user_path, f)
            for f in os.listdir(user_path)
            if re.match(r"EquityAwardsCenter_Transactions_.*\.json", f)
        ]
        if not transactions_files:
            pytest.skip(
                f"No valid transactions files found in {user_folder}, skipping test"
            )
        transaction_file = transactions_files[0]
        with open(transaction_file, "r", encoding="utf-8") as f:
            transactions = plugin_read(f, transaction_file, "schwab-json")

        holdings = do_holdings(
            "schwab",
            [transactions],
            2024,
            verbose=True,
        )

        report2024, holdings2024, _, summary2024 = tax_report(
            2024,
            "schwab",
            transactions,
            [],
            holdings,
            portfolio_engine=True,
            verbose=True,
            feature_flags=[],
        )

        snapshot_data = {
            "holdings2023_year": holdings2024.year,
            "holdings2023_broker": holdings2024.broker,
            "holdings2023_stocks": dump_list(holdings2024.stocks),
            "holdings2023_cash": dump_list(holdings2024.cash),
            "report2024_eoy_balance": {
                year: dump_list(items) for year, items in report2024.eoy_balance.items()
            },
            "report2024_ledger": {
                key: dump_list(value) for key, value in report2024.ledger.items()
            },
            "report2024_dividends": dump_list(report2024.dividends),
            "report2024_buys": dump_list(report2024.buys),
            "report2024_sales": {
                key: dump_list(sales_list)
                for key, sales_list in report2024.sales.items()
            },
            "report2024_cash_ledger": dump_list(report2024.cash_ledger),
            "report2024_unmatched_wires": dump_list(report2024.unmatched_wires),
        }

        serialized_snapshot_data = serialize_snapshot_data(snapshot_data)
        snapshot.assert_match(
            json.dumps(serialized_snapshot_data, indent=4, default=str),
            "holdings_consistency_snapshot_user",
        )


def serialized_list(item):
    return item.model_dump() if hasattr(item, "model_dump") else item


def dump_list(items):
    return [serialized_list(item) for item in items]


def serialize_snapshot_data(data):
    if isinstance(data, dict):
        return {key: serialize_snapshot_data(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [serialize_snapshot_data(item) for item in data]
    elif isinstance(data, date):
        return data.isoformat()
    elif isinstance(data, Decimal):
        return str(data)
    else:
        return data


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
