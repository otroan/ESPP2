'''
ESPPv2
'''

import argparse
import logging
from decimal import Decimal
from importlib.resources import files
import simplejson as json
from espp2.positions import Positions, Cash

logger = logging.getLogger(__name__)

def get_arguments():
    '''Get command line arguments'''

    description='''
    ESPP 2 Transactions Normalizer.
    '''
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--transaction-file',
                        type=argparse.FileType('r'), required=True)
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

def main():
    '''Main function'''
    args, logger = get_arguments()

    taxdata_file = files('espp2').joinpath('taxdata.json')
    with open(taxdata_file, 'r') as jf:
        taxdata = json.load(jf)

    transactions = json_load(args.transaction_file)
    wires = {}
    if args.wire_file:
        wires = json_load(args.wire_file)

    if args.inholdings_file:
        prev_holdings = json_load(args.inholdings_file)
    else:
        prev_holdings = None

    # TODO: Pre-calculate holdings if required
    p = Positions(args.year, taxdata, prev_holdings, transactions)
    c = Cash(args.year, transactions, wires)

    report = {}

    # End of Year Balance (formueskatt)
    prev_year_eoy = p.eoy_balance(args.year-1)
    this_year_eoy = p.eoy_balance(args.year)
    report['eoy_balance'] = {args.year - 1: prev_year_eoy,
                             args.year: this_year_eoy}

    report['dividends'] = p.dividends()
    report['buys'] = p.buys()
    report['sales'] = p.sales()

    # Cash and wires
    nomatch = c.wire()
    report['unmatched_wires'] = nomatch
    report['cash'] = c.process()

    # New holdings
    if args.outholdings_file:
        holdings = p.holdings(args.year, 'schwab')
        json.dump(holdings, args.outholdings_file, indent=4)

    # Tax report (in JSON)
    json.dump(report, args.output_file, indent=4)

if __name__ == '__main__':
    main()
