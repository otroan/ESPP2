'''
ESPPv2 Wrapper
'''

# pylint: disable=invalid-name
import os
import sys
import argparse
import logging
import typer
from pathlib import Path
from enum import Enum
from espp2.main import do_taxes
from espp2.datamodels import TaxReport, Holdings
from espp2.report import print_report

app = typer.Typer()

class BrokerEnum(str, Enum):
    '''BrokerEnum'''
    schwab = 'schwab'
    td = 'td'
    morgan = 'morgan'

logger = logging.getLogger(__name__)

@app.command()
def main(transaction_files: list[typer.FileBinaryRead],
         output: typer.FileTextWrite = None,
         year: int = 2022,
         broker: BrokerEnum = BrokerEnum.schwab,
         wires: typer.FileText = None,
         inholdings: typer.FileText = None,
         outholdings: typer.FileTextWrite = None,
         print: bool = False,
         loglevel: str = typer.Option("WARNING", help='Logging level')):

    '''ESPPv2 tax reporting tool'''
    lognames = logging.getLevelNamesMapping()
    if loglevel not in lognames:
        raise typer.BadParameter(f'Invalid loglevel: {loglevel}')
    logging.basicConfig(level=lognames[loglevel])

    report: TaxReport
    holdings: Holdings
    report, holdings = do_taxes(broker, transaction_files, inholdings, wires, year)

    if print:
        print_report(year, report, holdings)

    # New holdings
    if outholdings:
        logger.info('Writing new holdings to %s', outholdings.name)
        j = holdings.json(indent=4)
        with outholdings as f:
            f.write(j)

    # Tax report (in JSON)
    if output:
        j = report.json(indent=4)
        logger.info('Writing tax report to: %s', output.name)
        with output as f:
            f.write(j)

if __name__ == '__main__':
    app()
