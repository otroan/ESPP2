'''
ESPPv2 Wrapper
'''

# pylint: disable=invalid-name
import sys
import argparse
import logging
import typer
from pathlib import Path
from enum import Enum
from espp2.main import do_taxes
from espp2.datamodels import TaxReport, Holdings

app = typer.Typer()

class BrokerEnum(str, Enum):
    '''BrokerEnum'''
    schwab = 'schwab'
    td = 'td'
    morgan = 'morgan'
class TFormatEnum(str, Enum):
    '''Transaction Format Enum'''
    schwab = 'schwab'
    td = 'td'
    morgan = 'morgan'
    pickle = 'pickle'

logger = logging.getLogger(__name__)

def parse_option(values: list[str]) -> list[dict]:
    '''Parse transaction files option'''
    result = []
    for e in values:
        tformat, tfile = e.split(':')
        try:
            tformat_enum = TFormatEnum(tformat)
        except ValueError as e:
            raise typer.BadParameter(f'Invalid format: {tformat}') from e
        if tformat_enum == TFormatEnum.pickle:
            fd = open(tfile, 'rb')
        else:
            fd = open(tfile, 'r', encoding='utf-8')
        result.append({'fd': fd, 'format': tformat, 'name': tfile})
    return result

@app.command()
def main(transactions: list[str] = typer.Argument(..., help='List of transactions file in <format>:<file> format', callback=parse_option),
         output: typer.FileTextWrite = typer.Argument(..., help='Output file',),
         year: int = 2022,
         broker: BrokerEnum = BrokerEnum.schwab,
         wires: typer.FileText = None,
         inholdings: typer.FileText = None,
         outholdings: typer.FileTextWrite = None,
         loglevel: str = typer.Option("WARNING", help='Logging level')):

    '''ESPPv2 tax reporting tool'''
    lognames = logging.getLevelNamesMapping()
    if loglevel not in lognames:
        raise typer.BadParameter(f'Invalid loglevel: {loglevel}')
    logging.basicConfig(level=lognames[loglevel])

    report: TaxReport
    holdings: Holdings
    report, holdings = do_taxes(broker, transactions, inholdings, wires, year)

    # New holdings
    if outholdings:
        logger.info('Writing new holdings to %s', outholdings.name)
        j = holdings.json(indent=4)
        with outholdings as f:
            f.write(j)

    # Tax report (in JSON)
    j = report.json(indent=4)
    logger.info('Writing tax report to: %s', output.name)
    with output as f:
        f.write(j)

if __name__ == '__main__':
    app()
