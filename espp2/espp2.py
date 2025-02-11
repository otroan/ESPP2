"""
ESPPv2 Wrapper
"""

# pylint: disable=invalid-name

import os
import logging
from enum import Enum
import typer
import math
from rich.logging import RichHandler
from pydantic import TypeAdapter
from espp2.main import (
    do_taxes,
    do_holdings_1,
    do_holdings_4,
    console,
    get_zipdata,
)
from espp2.datamodels import Holdings, Wires
from espp2.report import print_report
from espp2._version import __version__
from espp2.util import FeatureFlagEnum

app = typer.Typer(pretty_exceptions_enable=False)

class BrokerEnum(str, Enum):
    """BrokerEnum"""

    schwab = "schwab"
    # td = "td"
    morgan = "morgan"


logger = logging.getLogger(__name__)


def version_callback(value: bool):
    if value:
        typer.echo(f"espp2 CLI Version: {__version__}")
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
):
    """ESPPv2 tax reporting tool"""
    lognames = logging.getLevelNamesMapping()
    if loglevel not in lognames:
        raise typer.BadParameter(f"Invalid loglevel: {loglevel}")

    logging.basicConfig(
        level=lognames[loglevel], handlers=[RichHandler(rich_tracebacks=False)]
    )

    result = None

    if inholdings:
        # Check inholdings are valid for previous tax year
        # if len(transaction_files) > 1:
        #     raise typer.BadParameter(
        #         "Cannot use inholdings with multiple transaction files"
        #     )
        result = do_taxes(
            broker,
            transaction_files,
            inholdings,
            wires,
            year,
            portfolio_engine=portfolio_engine,
            verbose=verbose,
            feature_flags=features
        )
        print_report(year, result.summary, result.report, result.holdings, verbose)
    else:
        if broker == BrokerEnum.morgan:
            holdings = do_holdings_4(
                broker, transaction_files[0], year, verbose=verbose
            )

        else:
            console.print(
                f"Generating holdings for previous tax year {year-1}",
                style="bold green",
            )
            holdings = do_holdings_1(
                broker,
                transaction_files,
                inholdings,
                year,
                portfolio_engine,
                verbose=verbose,
            )
        if not holdings or not holdings.stocks:
            logger.error("No holdings found")
            if len(transaction_files) > 1:
                raise typer.BadParameter(
                    "Cannot use inholdings with multiple transaction files"
                )

            result = do_taxes(
                broker,
                transaction_files[0],
                inholdings,
                wires,
                year,
                portfolio_engine=portfolio_engine,
                verbose=verbose,
            )
            print_report(year, result.summary, result.report, result.holdings, verbose)

    # New holdings
    if outholdings:
        holdings = result.holdings if result else holdings
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
            w.nok_value = math.nan
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
