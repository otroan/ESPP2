'''
ESPPv2
'''

import importlib
import argparse
import simplejson as json
import logging
import pandas as pd
import numpy as np
import IPython
import pprint
from fmv import FMV
from itertools import groupby
from copy import deepcopy
from decimal import Decimal

logger = logging.getLogger(__name__)

def position_groupby(data):
    '''Group data by symbol'''
    sorted_data = sorted(data, key=lambda x: x['symbol'])
    by_symbols = {}
    for k, g in groupby(sorted_data, key=lambda x: x['symbol']):
        by_symbols[k] = list(g)
    return by_symbols

class Positions():
    '''
    Keep track of stock positions. Expect transactions for this year and holdings from previous year.
    This is a singleton.
    '''
    _instance = None

    def __new__(cls, prev_holdings=None, transactions=None):
        if cls._instance is None:
            cls._instance = super(Positions, cls).__new__(cls)

            # Put any initialization here.
            cls.new_holdings = [t for t in transactions if t['type'] == 'BUY' or t['type'] == 'DEPOSIT']
            cls.positions = prev_holdings['stocks'] + cls.new_holdings
            cls.tax_deduction = []
            for i,p in enumerate(cls.positions):
                p['idx'] = i
                tax_deduction = p.get('tax_deduction', 0)
                cls.tax_deduction.insert(i, tax_deduction)

            cls.positions_by_symbols = position_groupby(cls.positions)
            cls.new_holdings_by_symbols = position_groupby(cls.new_holdings)
            cls.symbols = cls.positions_by_symbols.keys()

            # Sort sales
            sales = [t for t in transactions if t['type'] == 'SELL']
            cls.sale_by_symbols = position_groupby(sales)

            # Dividends
            cls.db_dividends = [t for t in transactions if t['type'] == 'DIVIDEND']
            cls.dividend_by_symbols = position_groupby(cls.db_dividends)

            # Tax
            cls.db_tax = [t for t in transactions if t['type'] == 'TAX']
            cls.tax_by_symbols = position_groupby(cls.db_tax)
            with open('taxdata.json', 'r') as jf:
                taxdata = json.load(jf)
            # cls.tax_deduction_rate = taxdata['tax_deduction_rates']
            cls.tax_deduction_rate = {year: Decimal(i[0]) for year, i in taxdata['tax_deduction_rates'].items()}
            print('TAX DETER', cls.tax_deduction_rate)
            # Wires
            cls.db_wires = [t for t in transactions if t['type'] == 'WIRE']

        return cls._instance

    def _balance(self, symbol, date):
        '''
        Return posisions by a given date. Returns a view as a copy.
        If changes are required use the update() function.
        '''
        # Copy positions
        posview = deepcopy(self.positions_by_symbols[symbol])
        posidx = 0
        for s in self.sale_by_symbols[symbol]:
            if s['date'] > date:
                break
            if posview[posidx]['date'] > date:
                raise Exception('Trying to sell stock from the future')
            qty_to_sell = abs(s['qty'])
            assert(qty_to_sell > 0)
            while qty_to_sell > 0:
                if posview[posidx]['qty'] == 0:
                    posidx += 1
                if qty_to_sell >= posview[posidx]['qty']:
                    qty_to_sell -= posview[posidx]['qty']
                    posview[posidx]['qty'] = 0
                    posidx += 1
                else:
                    posview[posidx]['qty'] -= qty_to_sell
                    qty_to_sell = 0
        return posview

    def __getitem__(self, val):
        '''
        Index 0: date slice
        Index 1: symbol
        '''
        enddate = val[0].stop
        b = self._balance(val[1], enddate)
        for i in b:
            if i['date'] < enddate:
                yield i
            else:
                break;                

    def update(self, index, fieldname, value):
        logger.debug('Entry update: %s %s %s', index, fieldname, value)
        self.positions[index][fieldname] = value

    def total_shares(self, iter):
        '''Returns total number of shares given an iterator (from __getitem__)'''
        total = Decimal(0)
        for i in iter:
            total += i['qty']
        return total

    def dividends(self):
        tax_deduction_used = 0

        dividend_usd = sum(item['amount']['value'] for item in self.db_dividends)
        dividend_nok = sum(item['amount']['nok_value'] for item in self.db_dividends)
        tax_usd = sum(item['amount']['value'] for item in self.db_tax)
        tax_nok = sum(item['amount']['nok_value'] for item in self.db_tax)

        for d in self.db_dividends:
            total_shares = self.total_shares(self[:d['date'], d['symbol']])
            if total_shares == 0:
                raise Exception('Total shares is zero.', d)
            dps = d['amount']['value'] / total_shares
            for entry in self[:d['date'], d['symbol']]: # Creates a view
                entry['dps'] = dps if 'dps' not in entry else entry['dps'] + dps
                tax_deduction = self.tax_deduction[entry['idx']]
                if tax_deduction > entry['dps']:
                    tax_deduction_used += (entry['dps'] * entry['qty'])
                    self.tax_deduction[entry['idx']] -= entry['dps']
                elif tax_deduction > 0:
                    tax_deduction_used += (tax_deduction * entry['qty'])
                    self.tax_deduction[entry['idx']] = 0
                self.update(entry['idx'], 'dps', entry['dps'])

        return {'dividend': {'value': dividend_usd, 'nok_value': dividend_nok},
                'tax': {'value': tax_usd, 'nok_value': tax_nok}, 'tax_deduction_used': tax_deduction_used}

    def individual_sale(self, sale_entry, buy_entry, qty):
        '''Calculate gain. Currently using total amount that includes fees.'''
        sale_price = sale_entry['amount']['value'] / abs(sale_entry['qty'])
        sale_price_nok = sale_price * sale_entry['amount']['nok_exchange_rate']
        gain = (sale_price_nok - buy_entry['purchase_price']['nok_value'])
        tax_deduction_used = 0
        tax_deduction = self.tax_deduction[buy_entry['idx']]
        if gain > 0:
            if gain > tax_deduction:
                gain -= tax_deduction
                tax_deduction_used = tax_deduction
                tax_deduction = 0
            else:
                tax_deduction_used = gain
                tax_deduction -= gain
                gain = 0
        if tax_deduction > 0:
            logger.info("Unused tax deduction: %s %d", buy_entry, gain)
        return {'qty': qty, "sale_price_nok": sale_price_nok, "purchase_price_nok": buy_entry['purchase_price']['nok_value'], 'gain': gain, 'tax_deduction_used': tax_deduction_used,
                'total_gain_nok': gain * qty, 'total_tax_deduction': tax_deduction_used * qty}

    def process_sale_for_symbol(self, symbol, sales, positions):
        posidx = 0
        sales_report = []
        c = Cash()
        p = Positions()

        for s in sales:
            qty_to_sell = abs(s['qty'])
            c.debit(s['date'], s['amount']['value'], s['amount']['nok_value'])

            while qty_to_sell > 0:
                if positions[posidx]['qty'] == 0:
                    posidx += 1
                if qty_to_sell >= positions[posidx]['qty']:
                    r = self.individual_sale(s, positions[posidx], positions[posidx]['qty'])
                    qty_to_sell -= positions[posidx]['qty']
                    positions[posidx]['qty'] = 0
                    posidx += 1
                else:
                    r = self.individual_sale(s, positions[posidx], qty_to_sell)
                    positions[posidx]['qty'] -= qty_to_sell
                    qty_to_sell = 0
                sales_report.append(r)
        return sales_report

    def sales(self):
        p = Positions()

        # Walk through all sales from transactions. Deducting from balance.
        sale_report = {}
        for symbol in p.sale_by_symbols:
            positions = deepcopy(p.positions_by_symbols[symbol])
            r = self.process_sale_for_symbol(symbol, p.sale_by_symbols[symbol], positions)
            total_gain = sum(item['total_gain_nok'] for item in r)
            total_tax_ded = sum(item['total_tax_deduction'] for item in r)
            total_sold = sum(item['qty'] for item in r)
            sale_report[symbol] = {'sales': r, 'gain': total_gain,
                                   'qty': total_sold, 'tax_deduction_used': total_tax_ded}

        return sale_report

    def buys(self):
        '''Return report of BUYS'''
        r = []
        for symbol in self.symbols:
            bought = sum(item['qty'] for item in self.new_holdings_by_symbols[symbol])
            price_sum = sum(item['purchase_price']['value'] for item in self.new_holdings_by_symbols[symbol])
            price_sum_nok = sum(item['purchase_price']['nok_value'] for item in self.new_holdings_by_symbols[symbol])
            avg_usd = price_sum/len(self.new_holdings_by_symbols[symbol])
            avg_nok = price_sum_nok/len(self.new_holdings_by_symbols[symbol])
            r.append({'symbol': symbol, 'qty': bought, 'avg_usd': avg_usd, 'avg_nok': avg_nok})
        return r

    def eoy_balance(self, year):
        '''End of year summary of holdings'''
        end_of_year = f'{year}-12-31'

        f = FMV()
        eoy_exchange_rate = f.get_currency('USD', end_of_year)
        r = []
        for symbol in self.symbols:
            eoy_balance = self[:end_of_year, symbol]
            total_shares = self.total_shares(eoy_balance)
            fmv = f[symbol, end_of_year]
            r.append({'symbol': symbol, 'qty': total_shares, 'total_nok': eoy_exchange_rate *
                     total_shares * fmv, 'nok_exchange_rate': eoy_exchange_rate, 'fmv': fmv})
        return r

    def holdings(self, year, broker):
        '''End of year positions in ESPP holdings format'''
        end_of_year = f'{year}-12-31'
        holdings = {}
        stocks = []
        for symbol in self.symbols:
            eoy_balance = self[:end_of_year, symbol]
            for item in eoy_balance:
                if item['qty'] == 0:
                    continue
                hitem = {}
                hitem['date'] = item['date']
                hitem['symbol'] = item['symbol']
                hitem['qty'] = item['qty']
                hitem['purchase_price'] = item['purchase_price'].copy()
                hitem['tax_deduction'] = self.tax_deduction[item['idx']]
                hitem['tax_deduction'] += (hitem['purchase_price']['nok_value'] * self.tax_deduction_rate[str(year)])/100
                stocks.append(hitem)
        holdings['year'] = year
        holdings['broker'] = broker
        holdings['stocks'] = stocks
        holdings['cash'] = []
        return holdings

    def wire(self):
        for w in self.db_wires:
            print('WWWW', w)

class Cash():
    ''' Cash balance.
    1) Cash USD Brokerage (per valuta)
    2) Hjemmebeholdning av valuta  (valutatrans)
    3) NOK hjemme
    '''
    _instance = None

    def __new__(cls, wire_filename=None):
        if cls._instance is None:
            cls._instance = super(Cash, cls).__new__(cls)

            # # Put any initialization here.
            cls.cash = []
            # cls.df = pd.DataFrame(columns=['type', 'symbol', 'date', 'qty', 'usdnok', 'amount_nok'])
            # cls.wire_filename = wire_filename
        return cls._instance

    def debit(self, date, amount, amount_nok):
        print('CASH DEBIT (buying USD):', date, amount, amount_nok)
        self.cash.append({'date': date, 'amount': amount, 'amount_nok': amount_nok})
        # self.df.loc[len(self.df.index)] = 'BUY', 'USD', date, qty, usdnok, np.nan

    def credit(self, date, qty):
        ''' TODO: Return usdnok rate for the item credited '''
        print('CASH CREDIT (selling USD):', date, qty)
        # self.df.loc[len(self.df.index)] = 'SELL', 'USD', date, qty, np.nan, np.nan

    def withdrawal(self, date, qty, usdnok, amount_nok):
        pass
        # self.df.loc[len(self.df.index)] = 'WIRE', 'USD', date, qty, usdnok, amount_nok

    def wire(self, wires):
        pass
        '''Merge wires rows with received NOK USD table'''

        # ### Separate directory for each
        # ###
        # logging.info(f'Reading wire received from {self.wire_filename}')
        # if not self.wire_filename or not os.path.isfile(self.wire_filename):
        #     logging.warning(f'No wire received file: {self.wire_filename}')
        #     return

        # dfr = pd.read_json(self.wire_filename)

        # w = wires[['type', 'symbol', 'date', 'amount']].copy()
        # w.sort_values(by='date', inplace=True)
        # w.reset_index(inplace=True)

        # if len(w) != len(dfr):
        #     raise Exception(f'Number of wires sent is different from received {w}\n{dfr}')
        # dfr['date'] = pd.to_datetime(dfr['date'], utc=True)
        # dfr.sort_values(by='date', inplace=True)
        # dfr.reset_index(inplace=True)

        # w['received_nok'] = dfr['amount']
        # w['received_date'] = dfr['date']
        # w['usdnok'] = abs(w['received_nok'] / w['amount'])

        # w['type'] = 'WIRE'

        # for i,r in w.iterrows():
        #     self.withdrawal(r.date, r.amount, r.usdnok, r.received_nok)

        # # TODO: Verify USD fields
        # # TODO: Raise exception if wire or received fields don't match
        # # IPython.embed()
        # return w

    def process(self):
        ''' Process the cash account.'''
        pass
        # sale = self.df[self.df.type.isin(['WIRE', 'SELL'])].sort_values(by='date')
        # df = self.df.copy()
        # dfr = pd.DataFrame(columns=['symbol', 'qty', 'open_date', 'open_price', 'close_date',
        #                             'close_price',  'sales_idx', 'idx'])

        # for si, sr in sale.iterrows():
        #     to_sell = abs(sr.qty)
        #     buys = df[df.type == 'BUY'].sort_values(by='date')
        #     for bi, br in buys.iterrows():
        #         if br.qty >= to_sell:
        #             df.loc[bi, 'qty'] -= to_sell
        #             no = to_sell
        #             to_sell = 0
        #         else:
        #             to_sell -= br.qty
        #             no = br.qty
        #             df.loc[bi, 'qty'] = 0
        #         if no > 0:
        #             dfr.loc[len(dfr.index)] = [sr['symbol'], no, br['date'],  br['usdnok'], sr['date'],
        #                                      sr['usdnok'], si, bi ]
        #         if to_sell == 0:
        #             break

        # if len(dfr) == 0:
        #     return None

        # def g(row):
        #     gain = row.close_price - row.open_price
        #     return gain * row.qty
        # dfr['total_gain_nok'] = dfr.apply(g, axis=1)

        # return dfr


def get_arguments():
    '''Get command line arguments'''

    description='''
    ESPP 2 Transactions Normalizer.
    '''
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--transaction-file',
                        type=argparse.FileType('r'), required=True)
    parser.add_argument('--holdings-file',
                        type=argparse.FileType('r'))
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

def main():
    '''Main function'''
    args, logger = get_arguments()
    transactions = json.load(args.transaction_file, parse_float=Decimal)
    if args.holdings_file:
        prev_holdings = json.load(args.holdings_file, parse_float=Decimal)
    else:
        prev_holdings = None

    # t = Transactions(int(args.year), prev_holdings, transactions)

    # TODO: Pre-calculate holdings if required
    p = Positions(prev_holdings, transactions)

    # End of Year Balance (formueskatt)
    print(f'End of year balance {args.year-1}:', p.eoy_balance(args.year-1))
    print(f'End of year balance {args.year}:', p.eoy_balance(args.year))

    # Dividends
    print('Dividends: ', p.dividends())

    # Sales
    print('Sales:', p.sales())

    # Buys (just for logging)
    print('Buys:', p.buys())

    # Cash
    # XXXX
    p.wire()

    # New holdings
    holdings = p.holdings(args.year, 'schwab')
    json.dump(holdings, args.output_file, indent=4)

if __name__ == '__main__':
    main()
