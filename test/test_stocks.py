from espp2.datamodels import Transactions
from espp2.positions import Ledger
from espp2.report import print_ledger
from rich.console import Console
from espp2.main import tax_report
from espp2.transactions import plugin_read
from espp2.espp2 import app
from typer.testing import CliRunner


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