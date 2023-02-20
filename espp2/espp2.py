'''
ESPPv2 Wrapper
'''
import sys
import argparse
import logging
from espp2.main import do_taxes
from espp2.datamodels import TaxReport, Holdings

# pylint: disable=invalid-name
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
    parser.add_argument('--broker', type=str, required=True)
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

supported_formats = ['schwab', 'td', 'morgan', 'norm', 'pickle']

def main():
    '''Main function'''
    args, logger = get_arguments()

    # Read and validate transaction files
    transaction_files = []
    for t in args.transaction_file:
        try:
            transformat, transaction_file = t.split(':')
        except ValueError:
            print(f'Invalid transaction file format {t} <format>:<file> required.')
            print(f'Supported formats: {supported_formats}')
            return

        if transformat not in supported_formats:
            print(f'Unsupported transaction file format: {transformat}')
            print(f'Supported formats: {supported_formats}')
            return

        print(f'Reading transactions from {transformat}:{transaction_file}')
        if transformat == 'pickle':
            fdmode = 'rb'
        else:
            fdmode = 'r'
        try:
            fd = open(transaction_file, fdmode)
            transaction_files.append({'fd': fd, 'name': transaction_file, 'format': transformat})
        except FileNotFoundError:
            logger.exception('Could not open transaction file: %s', transaction_file)
            sys.exit(1)

    report: TaxReport
    holdings: Holdings
    report, holdings = do_taxes(
        args.broker, transaction_files, args.inholdings_file, args.wire_file, args.year)

    # New holdings
    if args.outholdings_file:
        logger.info('Writing new holdings to %s', args.outholdings_file.name)
        j = holdings.json(indent=4)
        with args.outholdings_file as f:
            f.write(j)

    # Tax report (in JSON)
    j = report.json(indent=4)
    logger.info('Writing tax report to %s', args.output_file.name)
    with args.output_file as f:
        f.write(j)

if __name__ == '__main__':
    main()
