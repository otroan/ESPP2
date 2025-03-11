from espp2.datamodels import Transactions, Holdings
from espp2.positions import Ledger
from espp2.report import print_ledger
from rich.console import Console
from espp2.main import tax_report, do_holdings
from espp2.transactions import plugin_read
from espp2.espp2 import app
from typer.testing import CliRunner
from datetime import datetime

import json
import os
import re
import pytest

runner = CliRunner()

# Test files:
# test/schwab1.json:
#   - Complete transactions from 2023 until 2025
#     Requires first to generate holdings for 2023, then tax generation for 2024


def test_full_run(tmp_path):
    holdings_2023 = tmp_path / "holdings-2023.json"

    # Run for 2023 to generate outholdings
    result = runner.invoke(
        app,
        [
            "test/schwab1.json",
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
            "test/schwab1.json",
            "--verbose",
            "--year=2024",
            "--inholdings",
            holdings_2023,
        ],
    )
    print("RESULT", result.stdout)
    assert result.exit_code == 0


def test_stock1(tmp_path):
    transfile = "test/schwab1.json"

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
        cash=new_holdings_data["cash"]
    )

def get_transactions_files() -> list[Transactions]:
    transactions_files = []
    pattern = r'EquityAwardsCenter_Transactions_.*\.json'
    for filename in os.listdir():
        if re.search(pattern, filename):
            transactions_files.append(filename)

    transactions_list = []
    for transactions_file in transactions_files:
        with open(transactions_file, "r", encoding="utf-8") as f:
            transactions = plugin_read(f, transactions_file, "schwab-json")
            transactions_list.append(transactions)

    return transactions_list

def test_holdings_consistency_between_generated_holdings_and_actual_for_entire_history():
    previous_year = datetime.now().year - 1
    previous_tax_year = previous_year - 1
    two_tax_years_ago = previous_tax_year - 1

    holdings_file = f'espp-holdings-{previous_tax_year}.json'
    holdings_file_previous_year = f'espp-holdings-{two_tax_years_ago}.json'

    previous_holdings = generated_holdings_file(holdings_file_previous_year)
    if (previous_holdings is None):
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

def test_holdings_consistency_between_generated_holdings_and_previous_year_transaction_file():
    previous_year = datetime.now().year - 1
    previous_tax_year = previous_year - 1
    two_tax_years_ago = previous_tax_year - 1

    holdings_file = f'espp-holdings-{previous_tax_year}.json'
    previous_holdings = generated_holdings_file(holdings_file)

    if (previous_holdings is None):
        pytest.skip("No previous holdings file found, skipping test")

    transactions = get_transactions_files()[-1]

    report_2024, new_holdings, excel_data_2024, summary_2024 = tax_report(
        2024,
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

def test_holdings_consistency_when_several_transaction_files():
    transactions_list = get_transactions_files()
    if not transactions_list:
        pytest.skip("No transactions files found, skipping test")

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

    previous_year = datetime.now().year - 2
    holdings_file = f'espp-holdings-{previous_year}.json'
    actual_holdings = generated_holdings_file(holdings_file)

    assert holdings2023.sum_qty() == actual_holdings.sum_qty()
    assert holdings2023.stocks[0].symbol == actual_holdings.stocks[0].symbol
