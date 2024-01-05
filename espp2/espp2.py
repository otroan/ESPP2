'''
ESPPv2 Wrapper
'''

# pylint: disable=invalid-name

import logging
from enum import Enum
import typer
from pydantic import TypeAdapter
from numpy import nan
from rich.logging import RichHandler
from espp2.main import do_taxes, do_holdings_2, do_holdings_1, do_holdings_3, do_holdings_4, console
from espp2.datamodels import Holdings, Wires, ExpectedBalance
from espp2.report import print_report
from espp2._version import __version__
from IPython import embed
app = typer.Typer(pretty_exceptions_enable=False)

class BrokerEnum(str, Enum):
    '''BrokerEnum'''
    schwab = 'schwab'
    td = 'td'
    morgan = 'morgan'

logger = logging.getLogger(__name__)

def version_callback(value: bool):
    if value:
        typer.echo(f"espp2 CLI Version: {__version__}")
        raise typer.Exit()
@app.command()
def main(transaction_files: list[typer.FileBinaryRead],
         output: typer.FileTextWrite = None,
         year: int = 2022,
         broker: BrokerEnum = BrokerEnum.schwab,
         wires: typer.FileText = None,
         inholdings: typer.FileText = None,
         outholdings: typer.FileTextWrite = None,
         outwires: typer.FileTextWrite = None,
         verbose: bool = False,
         opening_balance: str = None,
         loglevel: str = typer.Option("WARNING", help='Logging level'),
         version: bool = typer.Option(None, "--version", callback=version_callback, is_eager=True),
         preheat_cache: bool = False,
         expected_balance: str = None):

    '''ESPPv2 tax reporting tool'''
    lognames = logging.getLevelNamesMapping()
    if loglevel not in lognames:
        raise typer.BadParameter(f'Invalid loglevel: {loglevel}')
    logging.basicConfig(level=lognames[loglevel], handlers=[RichHandler(rich_tracebacks=False)])

    if opening_balance:
        adapter = TypeAdapter(Holdings)
        opening_balance= adapter.validate_json(opening_balance)
    result = None

    if preheat_cache:
        preheat_cache()

    if inholdings:
        # Check inholdings are valid for previous tax year
        if len(transaction_files) > 1:
            raise typer.BadParameter('Cannot use inholdings with multiple transaction files')
        result = do_taxes(broker, transaction_files[0], inholdings, wires, year, verbose=verbose,
                        opening_balance=opening_balance)
        print_report(year, result.summary, result.report, result.holdings, verbose)
    else:
        if broker == BrokerEnum.morgan:
            holdings = do_holdings_4(broker, transaction_files[0], year, verbose=verbose)

        elif expected_balance:
            adapter = TypeAdapter(ExpectedBalance)
            expected_balance = adapter.validate_json(expected_balance)
            console.print('Generating holdings from expected balance', style='bold green')
            if len(transaction_files) > 1:
                logger.warning("This does not work with reinvested dividends!")
                holdings = do_holdings_2(broker, transaction_files, year, expected_balance, verbose=verbose)
            else:
                holdings = do_holdings_3(broker, transaction_files[0], year, expected_balance=expected_balance, verbose=verbose)
        else:
            console.print(
                f'Generating holdings for previous tax year {year-1}', style='bold green')
            holdings = do_holdings_1(broker, transaction_files, inholdings,
                                     year, opening_balance=opening_balance, verbose=verbose)
        if not holdings or not holdings.stocks:
            logger.error('No holdings found')
            if len(transaction_files) > 1:
                raise typer.BadParameter('Cannot use inholdings with multiple transaction files')

            result = do_taxes(broker, transaction_files[0], inholdings, wires, year, verbose=verbose,
                            opening_balance=opening_balance)
            print_report(year, result.summary, result.report, result.holdings, verbose)

    # New holdings
    if outholdings:
        holdings = result.holdings if result else holdings
        logger.info('Writing new holdings to %s', outholdings.name)
        j = holdings.model_dump_json(indent=4)
        with outholdings as f:
            f.write(j)
    else:
        console.print('No new holdings file specified', style='bold red')
    if outwires and result and result.report and result.report.unmatched_wires:
        logger.info('Writing unmatched wires to %s', outwires.name)
        outw = Wires(result.report.unmatched_wires)
        for w in outw:
            w.nok_value = nan
            w.value = abs(w.value)
        j = outw.model_dump_json(indent=4)
        with outwires as f:
            f.write(j)

    # Tax report (in JSON)
    if output:
        j = result.report.model_dump_json(indent=4)
        logger.info('Writing tax report to: %s', output.name)
        with output as f:
            f.write(j)

if __name__ == '__main__':
    app()
