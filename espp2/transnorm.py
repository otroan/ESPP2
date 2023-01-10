#!/usr/bin/env python3

'''
Normalize transaction history.

Supported importers:
 - Schwab Equity Awards CSV
 - TD Ameritrade CSV
 - Manual input
'''

import importlib
import argparse
import logging
import simplejson as json

def get_arguments():
    '''Get command line arguments'''

    description='''
    ESPP 2 Transactions Normalizer.
    '''
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--format', type=str, help='Which broker format',
                        choices=['schwab', 'td', 'manual'], required=True)
    parser.add_argument('--transaction-file',
                        type=argparse.FileType('r'), required=True)
    parser.add_argument(
        '--output-file', type=argparse.FileType('w'), required=True)
    parser.add_argument(
        "-log",
        "--log",
        default="warning",
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

def main():
    '''Main function'''

    args, logger = get_arguments()
    args.format = 'espp2.plugins.' + args.format
    plugin = importlib.import_module(args.format, package='espp2')
    transactions = plugin.read(args.transaction_file.name, logger)
    json.dump(transactions, args.output_file, use_decimal=True, indent=4)

if __name__ == '__main__':
    main()
