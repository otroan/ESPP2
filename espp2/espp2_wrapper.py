'''
ESPPv2 Wrapper
'''

import argparse
import logging
from decimal import Decimal
from importlib.resources import files
import simplejson as json
from espp2.positions import Positions, Cash, Wires
from espp2.transnorm import normalize
from espp2.main import tax_report, do_taxes, Log
import sys
import IPython

logger = logging.getLogger(__name__)

def get_arguments():
    '''Get command line arguments'''

    description='''
    ESPP 2 Main Wrapper Program.
    '''
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--transaction-file',
                        help='List of transactions file in <format>:<file> format',
                        nargs='+', required=True)
    parser.add_argument('--wire-file',
                        type=argparse.FileType('r'))
    parser.add_argument('--inholdings-file',
                        type=argparse.FileType('r'))
    parser.add_argument('--outholdings-file',
                        type=argparse.FileType('w'))
    parser.add_argument(
        '--output-file', type=argparse.FileType('w'), required=True)
    parser.add_argument('--year', type=int, required=True)
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

def json_load(fp):
    data = json.load(fp, parse_float=Decimal)
    return data

supported_formats = ['schwab', 'td', 'morgan', 'norm', 'pickle']

def main():
    '''Main function'''
    args, logger = get_arguments()

    taxdata_file = files('espp2').joinpath('taxdata.json')
    with open(taxdata_file, 'r', encoding='utf-8') as jf:
        taxdata = json.load(jf)

    # Read and validate transaction files
    transactions = []
    for t in args.transaction_file:
        try:
            format, transaction_file = t.split(':')
        except ValueError:
            print(f'Invalid transaction file format {t} <format>:<file> required.')
            print(f'Supported formats: {supported_formats}')
            return

        if format not in supported_formats:
            print(f'Unsupported transaction file format: {format}')
            print(f'Supported formats: {supported_formats}')
            return

        print(f'Reading transactions from {format}:{transaction_file}')
        with open(transaction_file, 'rb') as fd:
            trans_object, trans = normalize(format, fd, logger)
        
        transactions += trans

    wires = {}
    if args.wire_file:
        print(f'Reading wire transactions from {args.wire_file.name}')
        wires = json_load(args.wire_file)
        wires = Wires(wires=wires)
        print(f'Wires: {wires}')

    if args.inholdings_file:
        print(f'Reading previous holdings from {args.wire_file.name}')
        prev_holdings = json_load(args.inholdings_file)
    else:
        prev_holdings = None
    log = Log()

    report, holdings = tax_report(args.year, transactions, wires, prev_holdings, taxdata, log)

    # New holdings
    if args.outholdings_file:
        json.dump(holdings, args.outholdings_file, indent=4)

    # Tax report (in JSON)
    json.dump(report, args.output_file, indent=4)

if __name__ == '__main__':
    main()
