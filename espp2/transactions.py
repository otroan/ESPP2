# pylint: disable=invalid-name

'''
Normalize transaction history.

Supported importers:
 - Schwab Equity Awards CSV
 - TD Ameritrade CSV
 - Morgan Stanley HTML tables
 - Manual input
 - Old pickle-file format (With caveats)
'''

import os
import importlib
import argparse
import logging
from typing import Union
import typer
from fastapi import UploadFile
import starlette
from espp2.datamodels import Transactions

logger = logging.getLogger(__name__)

def get_arguments():
    '''Get command line arguments'''

    description='''
    ESPP 2 Transactions Normalizer.
    '''
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--format', type=str, help='Which broker format',
                        choices=['schwab', 'td', 'morgan', 'pickle'],
                        required=True)
    parser.add_argument('--transaction-file',
                        type=argparse.FileType('rb'), required=True)
    parser.add_argument(
        '--output-file', type=argparse.FileType('w'), required=True)
    parser.add_argument(
        "--log",
        default="debug",
        help=(
            "Provide logging level. "
            "Example --log debug', default='warning'"),
    )

    options = parser.parse_args()
    levels = {
        'critical': logging.CRITICAL,
        'error': logging.ERROR,
        'warn': logging.WARNING,
        'warning': logging.WARNING,
        'info': logging.INFO,
        'debug': logging.DEBUG
    }
    level = levels.get(options.log.lower())

    if level is None:
        raise ValueError(
        f"log level given: {options.log}"
        f" -- must be one of: {' | '.join(levels.keys())}")

    logging.basicConfig(level=level)
    logger = logging.getLogger(__name__)

    return parser.parse_args(), logger

def guess_format(filename, data) -> str:
    '''Guess format'''
    fname, extension = os.path.splitext(filename)
    if extension == '.pickle':
        return 'pickle'

    if extension == '.html' and data.read(1) == b'<':
        data.seek(0)
        return 'morgan'

    # Assume CSV
    data.seek(0)
    if data.read(20) == b'"Transaction Details':
        data.seek(0)
        return 'schwab'

    data.seek(0)
    if data.read(16) == b'DATE,TRANSACTION':
        data.seek(0)
        return 'td'
    raise ValueError('Unable to guess format', fname, extension)

def normalize(data: Union[UploadFile, typer.FileText]) -> Transactions:
    '''Normalize transactions'''
    if isinstance(data, starlette.datastructures.UploadFile):
        filename = data.filename
        fd = data.file
    else:
        filename = data.name
        fd = data
    trans_format = guess_format(filename, fd)

    plugin_path = 'espp2.plugins.' + trans_format
    plugin = importlib.import_module(plugin_path, package='espp2')
    logger.info('Importing transactions with importer %s: %s', trans_format, filename)
    return plugin.read(fd, filename, logger)
