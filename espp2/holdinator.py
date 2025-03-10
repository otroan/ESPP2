"""
Re-generate holdings from transaction files
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
    do_holdings_1,
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
    schwab_individual = "schwab-individual"


logger = logging.getLogger(__name__)


def version_callback(value: bool):
    if value:
        typer.echo(f"espp2 CLI Version: {__version__}")
        raise typer.Exit()


@app.command()
def main(  # noqa: C901
    transaction_files: list[typer.FileBinaryRead],
    outholdings: typer.FileTextWrite,
    year: int = 2024,
    broker: BrokerEnum = BrokerEnum.schwab,
    verbose: bool = False,
    loglevel: str = typer.Option("WARNING", help="Logging level"),
    version: bool = typer.Option(
        None, "--version", callback=version_callback, is_eager=True
    ),
):
    """Holdinator: Re-generate holdings from transaction files"""
    lognames = logging.getLevelNamesMapping()
    if loglevel not in lognames:
        raise typer.BadParameter(f"Invalid loglevel: {loglevel}")

    print(f'{outholdings}')
    logging.basicConfig(
        level=lognames[loglevel], handlers=[RichHandler(rich_tracebacks=False)]
    )

    holdings = do_holdings_1(
        broker,
        transaction_files,
        year,
        verbose=verbose,
    )

    # New holdings
    if outholdings:
        logger.info("Writing new holdings to %s", outholdings.name)
        j = holdings.model_dump_json(indent=4)
        with outholdings as f:
            f.write(j)


if __name__ == "__main__":
    app()
