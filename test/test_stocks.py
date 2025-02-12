from espp2.datamodels import Transactions
from espp2.positions import Ledger
from espp2.report import print_ledger
from rich.console import Console
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
        app, ["test/schwab1.json", "--verbose", "--year=2023", "--outholdings", holdings_2023]
    )
    print('RESULT', result.stdout)
    assert result.exit_code == 0

    result = runner.invoke(
        app, ["test/schwab1.json", "--verbose", "--year=2024", "--inholdings", holdings_2023]
    )
    print('RESULT', result.stdout)
    assert result.exit_code == 0
