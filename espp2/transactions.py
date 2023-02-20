#!/usr/bin/env python3

'''
Normalize transaction history.

Supported importers:
 - Schwab Equity Awards CSV
 - TD Ameritrade CSV
 - Morgan Stanley HTML tables
 - Manual input
 - Old pickle-file format (With caveats)
'''

import importlib
import argparse
import logging
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

def normalize(trans_format, data):
    '''Normalize transactions'''
    trans_format = 'espp2.plugins.' + trans_format
    plugin = importlib.import_module(trans_format, package='espp2')
    logger.info(f'Importing transactions with importer {trans_format} {data.name}')
    transactions = plugin.read(data, logger)
    if isinstance(transactions, Transactions):
        return transactions
    sorted_transactions = sorted(transactions, key=lambda d: d['date'])
    logger.info(
        f'Imported {len(sorted_transactions)} transactions, starting {sorted_transactions[0]["date"]}, ending {sorted_transactions[-1]["date"]}.''')
    # Validate transactions
    return Transactions(transactions=sorted_transactions)

def main():
    '''Main function'''
    args, logger = get_arguments()
    logger.debug('Arguments: %s', args)
    trans_obj, _ = normalize(args.format, args.transaction_file)
    logger.info('Converting to JSON')
    j = trans_obj.json(indent=4)

    logger.info(f'Writing transaction file to: {args.output_file.name}')
    with args.output_file as f:
        f.write(j)

if __name__ == '__main__':
    main()
