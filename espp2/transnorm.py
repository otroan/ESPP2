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
import simplejson as json
from pydantic import BaseModel, ValidationError, validator, Field
from datetime import datetime, date
from typing import List, Literal, Annotated, Union, Optional, Any
from enum import Enum
from devtools import debug
from decimal import Decimal


'''
Transactions data model
'''
class EntryTypeEnum(str, Enum):
    BUY = 'BUY'
    DEPOSIT = 'DEPOSIT'
    TAX = 'TAX'
    TAXSUB = 'TAXSUB'
    DIVIDEND = 'DIVIDEND'
    DIVIDEND_REINV = 'DIVIDEND_REINV'
    WIRE = 'WIRE'
    SELL = 'SELL'

class Amount(BaseModel):
    currency: str
    nok_exchange_rate: Decimal
    nok_value: Decimal
    value: Decimal
class Buy(BaseModel):
    type: Literal[EntryTypeEnum.BUY]
    date: date
    symbol: str
    qty: Decimal

class Deposit(BaseModel):
    type: Literal[EntryTypeEnum.DEPOSIT]
    date: date
    qty: Decimal
    symbol: str
    description: str
    purchase_price: Amount
    purchase_date: date = None

class Tax(BaseModel):
    type: Literal[EntryTypeEnum.TAX]
    date: date
    symbol: str
    description: str
    amount: Amount

class Taxsub(BaseModel):
    type: Literal[EntryTypeEnum.TAXSUB]
    date: date
    symbol: str
    description: str
    amount: Amount

class Dividend(BaseModel):
    type: Literal[EntryTypeEnum.DIVIDEND]
    date: date
class Dividend_Reinv(BaseModel):
    type: Literal[EntryTypeEnum.DIVIDEND_REINV]
    date: date
    symbol: str
    amount: Amount
    description: str
class Wire(BaseModel):
    type: Literal[EntryTypeEnum.WIRE]
    date: date
    amount: Amount
    description: str
    fee: Optional[Amount]
class Sell(BaseModel):
    type: Literal[EntryTypeEnum.SELL]
    date: date
    symbol: str
    qty: Decimal
    fee: Optional[Amount]
    amount: Amount
    description: str

# Deposits = Annotated[Union[ESPP, RS], Field(discriminator="description")] | Deposit
Entry = Annotated[Union[Buy, Deposit, Tax, Taxsub, Dividend, Dividend_Reinv, Wire, Sell], Field(discriminator="type")]
class Transactions(BaseModel):
    transactions: list[Entry]

def get_arguments():
    '''Get command line arguments'''

    description='''
    ESPP 2 Transactions Normalizer.
    '''
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--format', type=str, help='Which broker format',
                        choices=['schwab', 'td', 'manual', 'pickle'],
                        required=True)
    parser.add_argument('--transaction-file',
                        type=argparse.FileType('rb'), required=True)
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

def transnorm(format, transactions_file, logger):
    format = 'espp2.plugins.' + format
    plugin = importlib.import_module(format, package='espp2')
    transactions = plugin.read(transactions_file, logger)
    return transactions

def normalize(format, data, logger):
    format = 'espp2.plugins.' + format
    plugin = importlib.import_module(format, package='espp2')
    transactions = plugin.read(data, logger)
    sorted_transactions = sorted(transactions, key=lambda d: d['date'])
    # print('TRANSA BEFORE VALIDATION', sorted_transactions)
    return Transactions(transactions=sorted_transactions), sorted_transactions

def main():
    '''Main function'''
    args, logger = get_arguments()
    transactions = transnorm(args.format, args.transaction_file, logger)
    json.dump(transactions, args.output_file, use_decimal=True, indent=4)

if __name__ == '__main__':
    main()
