"""
ESPPv2 Wrapper
"""

# pylint: disable=invalid-name

import logging
from enum import Enum
import typer
from rich.logging import RichHandler
from espp2.main import (
    do_taxes,
    console,
    get_zipdata,
)
from espp2.datamodels import Wires, EOYBalanceComparison
from espp2.report import print_report
from espp2.util import FeatureFlagEnum
from espp2 import __version__
from decimal import Decimal

app = typer.Typer(pretty_exceptions_enable=False)


class BrokerEnum(str, Enum):
    """BrokerEnum"""

    schwab = "schwab"
    # td = "td"
    morgan = "morgan"
    schwab_individual = "schwab-individual"


logger = logging.getLogger(__name__)


def version_callback(value: bool):
    if value:
        typer.echo(f"espp2 CLI version: {__version__}")
        raise typer.Exit()


@app.command()
def main(  # noqa: C901
    transaction_files: list[typer.FileBinaryRead],
    output: typer.FileBinaryWrite = None,
    year: int = 2024,
    broker: BrokerEnum = BrokerEnum.schwab,
    wires: typer.FileText = None,
    inholdings: typer.FileText = None,
    outholdings: typer.FileTextWrite = None,
    outwires: typer.FileTextWrite = None,
    verbose: bool = False,
    portfolio_engine: bool = True,
    features: list[FeatureFlagEnum] = typer.Option([], help="Features to enable"),
    loglevel: str = typer.Option("WARNING", help="Logging level"),
    version: bool = typer.Option(
        None, "--version", callback=version_callback, is_eager=True
    ),
    openingcash: float = None,
):
    """ESPPv2 tax reporting tool"""
    lognames = logging.getLevelNamesMapping()
    if loglevel not in lognames:
        raise typer.BadParameter(f"Invalid loglevel: {loglevel}")

    logging.basicConfig(
        level=lognames[loglevel], handlers=[RichHandler(rich_tracebacks=False)]
    )

    # Create EOYBalanceComparison object if openingcash is provided
    eoy_balance = None
    if openingcash is not None:
        logger.info(f"Using provided opening cash: {openingcash:.2f}")
        try:
            eoy_balance = [
                EOYBalanceComparison(year=year - 1, cash_qty=Decimal(str(openingcash)))
            ]
        except Exception as e:
            logger.error(f"Error creating EOYBalanceComparison from opening cash: {e}")
            raise typer.Exit(code=1)

    result = None
    result = do_taxes(
        broker,
        transaction_files,
        inholdings,
        wires,
        year,
        portfolio_engine=portfolio_engine,
        verbose=verbose,
        feature_flags=features,
        eoy_balance=eoy_balance,
    )
    print_report(year, result.summary, result.report, result.holdings, verbose)

    # New holdings
    if outholdings:
        holdings = result.holdings
        logger.info("Writing new holdings to %s", outholdings.name)
        j = holdings.model_dump_json(indent=4)
        with outholdings as f:
            f.write(j)
    else:
        console.print("No new holdings file specified", style="bold red")
    if outwires and result and result.report and result.report.unmatched_wires:
        logger.info("Writing unmatched wires to %s", outwires.name)
        outw = Wires(result.report.unmatched_wires)
        for w in outw:
            w.nok_value = None
            w.value = abs(w.value)
        j = outw.model_dump_json(indent=4)
        with outwires as f:
            f.write(j)

    # Tax report (in ZIP)
    if output:
        j = result.report.model_dump_json(indent=4)
        logger.info("Writing tax report to: %s", output.name)
        zipdata = get_zipdata(
            [
                (
                    f"espp-holdings-{year}.json",
                    result.holdings.model_dump_json(indent=4),
                ),
                (f"espp-portfolio-{year}.xlsx", result.excel),
            ]
        )

        with output as f:
            f.write(zipdata)


if __name__ == "__main__":
    app()
