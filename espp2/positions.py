'''
ESPPv2 Positions module
'''

import argparse
import logging
from itertools import groupby
from copy import deepcopy
from datetime import datetime
from math import isclose
import IPython
from decimal import Decimal, getcontext
from espp2.fmv import FMV

getcontext().prec = 6

logger = logging.getLogger(__name__)

def position_groupby(data):
    '''Group data by symbol'''
    sorted_data = sorted(data, key=lambda x: x['symbol'])
    by_symbols = {}
    for k, g in groupby(sorted_data, key=lambda x: x['symbol']):
        by_symbols[k] = list(g)
    return by_symbols

def todate(datestr: str) -> datetime:
    return datetime.strptime(datestr, '%Y-%m-%d')

# TODO:
#
# - Check for duplicates or overlapping positions.
# - Validate against data model schema (transactions and holdings)
# - Two gains calculation options.
#   - Tie sales to received money. No via USD calculation.
#   - Via cash account
# - Dump report in JSON
#
class Positions():
    '''
    Keep track of stock positions. Expect transactions for this year and holdings from previous year.
    This is a singleton.
    '''
    _instance = None

    def _fixup_tax_deductions(self):
        '''ESPP purchased last year but accounted this year deserves tax deduction'''
        for p in self.new_holdings:
            if p['type'] == 'DEPOSIT' and p['description'] == 'ESPP':
                if todate(p['date']).year - 1 == todate(p['purchase_date']).year:
                    year = todate(p['purchase_date']).year
                    p['tax_deduction'] = (self.tax_deduction_rate[str(year)] * p['purchase_price']['nok_value'])/100
                    logger.debug('Adding tax deduction for ESPP from last year %s', p)

    def __new__(cls, year=None, taxdata=None, prev_holdings=None, transactions=None, validate_year = 'exact'):
        if cls._instance is None:
            cls._instance = super(Positions, cls).__new__(cls)

            # Put any initialization here.
            if validate_year == 'exact':
                other_transactions = [t for t in transactions if todate(t['date']).year != year]
                if len(other_transactions):
                    raise Exception('Limit transactions to this year only', len(other_transactions))
            elif validate_year == 'filter':
                transactions = [t for t in transactions if todate(t['date']).year <= year]

            cls.tax_deduction_rate = {year: Decimal(str(i[0])) for year, i in taxdata['tax_deduction_rates'].items()}

            cls.new_holdings = [t for t in transactions if t['type'] == 'BUY' or t['type'] == 'DEPOSIT']
            cls._fixup_tax_deductions(cls)

            if prev_holdings and 'stocks' in prev_holdings:
                cls.positions = prev_holdings['stocks'] + cls.new_holdings
            else:
                logger.warning("No stocks in holding file?")
                cls.positions = cls.new_holdings

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

            cls.db_dividend_reinv = [t for t in transactions if t['type'] == 'DIVIDEND_REINV']
            cls.dividend_reinv_by_symbols = position_groupby(cls.db_dividend_reinv)

            # Tax
            cls.db_tax = [t for t in transactions if t['type'] == 'TAX']
            cls.db_taxsub = [t for t in transactions if t['type'] == 'TAXSUB']
            cls.tax_by_symbols = position_groupby(cls.db_tax)
            # cls.tax_deduction_rate = taxdata['tax_deduction_rates']

            # # Wires
            # cls.db_wires = [t for t in transactions if t['type'] == 'WIRE']

        return cls._instance

    def _balance(self, symbol, date):
        '''
        Return posisions by a given date. Returns a view as a copy.
        If changes are required use the update() function.
        '''
        # Copy positions
        posview = deepcopy(self.positions_by_symbols[symbol])
        posidx = 0
        if symbol in self.sale_by_symbols:
            for s in self.sale_by_symbols[symbol]:
                if todate(s['date']) > date:
                    break
                if todate(posview[posidx]['date']) > date:
                    raise Exception('Trying to sell stock from the future')
                qty_to_sell = abs(s['qty'])
                assert qty_to_sell > 0
                while qty_to_sell > 0:
                    if posidx >= len(posview):
                        raise Exception('Selling more shares than we hold', s, posview)
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
        enddate = todate(val[0].stop)
        b = self._balance(val[1], enddate)
        for i in b:
            if todate(i['date']) < enddate:
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
        c = Cash()
        tax_deduction_used = 0

        # TODO: By symbol?
        dividend_usd = sum(item['amount']['value'] for item in self.db_dividends)
        dividend_nok = sum(item['amount']['nok_value'] for item in self.db_dividends)
        tax_usd = sum(item['amount']['value'] for item in self.db_tax)
        tax_nok = sum(item['amount']['nok_value'] for item in self.db_tax)
        taxsub = sum(item['amount']['value'] for item in self.db_taxsub)
        taxsub_nok = sum(item['amount']['nok_value'] for item in self.db_taxsub)
        tax_usd -= taxsub
        tax_nok -= taxsub_nok

        # Deal with dividends and cash account
        for d in self.db_dividends:
            c.debit(d['date'], d['amount'])
        for t in self.db_tax:
            c.credit(t['date'], t['amount'])
        for i in self.db_dividend_reinv:
            c.credit(i['date'], i['amount'])

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
                'total_gain_nok': gain * qty, 'total_tax_deduction': tax_deduction_used * qty, 'total_purchase_price': buy_entry['purchase_price']['nok_value'] * qty}

    def process_sale_for_symbol(self, symbol, sales, positions):
        posidx = 0
        sales_report = []
        c = Cash()
        p = Positions()

        for s in sales:
            s_record = {'date': s['date'], 'qty': s['qty'], 'fee': s['fee'], 'amount': s['amount']}
            s_record['from_positions'] = []
            qty_to_sell = abs(s['qty'])
            c.debit(s['date'], s['amount'])

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
                s_record['from_positions'].append(r)

            total_gain = sum(item['total_gain_nok'] for item in s_record['from_positions'])
            total_tax_ded = sum(item['total_tax_deduction'] for item in s_record['from_positions'])
            total_sold = sum(item['qty'] for item in s_record['from_positions'])
            total_purchase_price = sum(item['total_purchase_price'] for item in s_record['from_positions'])
            total_purchase_price += s['fee']['nok_value']
            totals = {'gain': total_gain, 'sold_qty': total_sold, 'purchase_price': total_purchase_price, 'tax_ded': total_tax_ded,
            'sell_price': s['amount']['nok_value']}
            s_record['totals'] = totals
            sales_report.append(s_record)
        return sales_report

    def sales(self):
        p = Positions()

        # Walk through all sales from transactions. Deducting from balance.
        sale_report = {}
        for symbol in p.sale_by_symbols:
            totals = {}
            positions = deepcopy(p.positions_by_symbols[symbol])
            r = self.process_sale_for_symbol(symbol, p.sale_by_symbols[symbol], positions)
            sale_report[symbol] = r

            totals['gain'] = sum(item['totals']['gain'] for item in sale_report[symbol])
            totals['tax_ded'] = sum(item['totals']['tax_ded'] for item in sale_report[symbol])
            totals['sold_qty'] = sum(item['totals']['sold_qty'] for item in sale_report[symbol])
            totals['purchase_price'] = sum(item['totals']['purchase_price'] for item in sale_report[symbol])
            totals['sell_price'] = sum(item['totals']['sell_price'] for item in sale_report[symbol])
            sale_report['totals'] = totals

        return sale_report

    def buys(self):
        '''Return report of BUYS'''
        r = []
        c = Cash()
        for symbol in self.symbols:
            bought = 0
            price_sum = 0
            price_sum_nok = 0
            for item in self.new_holdings_by_symbols[symbol]:
                if item['type'] == 'BUY':
                    if 'amount' in item:
                        c.credit(item['date'], item['amount'])
                    else:
                        raise NotImplementedError
                        # item['purchase_price']['value'] * item['qty']
                        # c.credit(item['date'], item['purchase_price']['value'] * item['qty'])
                bought += item['qty']
                price_sum += item['purchase_price']['value']
                price_sum_nok += item['purchase_price']['nok_value']
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


class Cash():
    ''' Cash balance.
    1) Cash USD Brokerage (per valuta)
    2) Hjemmebeholdning av valuta  (valutatrans)
    3) NOK hjemme
    '''
    _instance = None

    def __new__(cls, year=None, transactions=None, wires=None):
        if cls._instance is None:
            cls._instance = super(Cash, cls).__new__(cls)

            # Put any initialization here.
            cls.db_wires = [t for t in transactions if t['type'] == 'WIRE']
            cls.db_received = wires
            cls.cash = []
        return cls._instance

    def sort(self):
        self.cash = sorted(self.cash, key=lambda d: d['date']) 

    def debit(self, date, amount,):
        logger.debug('Cash debit: %s: %s', date, amount['value'])
        self.cash.append({'date': date, 'amount': amount})
        self.sort()

    def credit(self, date, amount, transfer=False):
        ''' TODO: Return usdnok rate for the item credited '''
        logger.debug('Cash credit: %s: %s', date, amount['value'])
        self.cash.append({'date': date, 'amount': amount, 'transfer': transfer})
        self.sort()

    def _wire_match(self, wire):
        for v in self.db_received:
            if v['date'] == wire['date'] and isclose(v['usd_sent'], abs(wire['amount']['value']), abs_tol = 0.05):
                return v

    def wire(self):
        '''Process wires from sent and received (manual) records'''
        unmatched = []
        for w in self.db_wires:
            match = self._wire_match(w)
            if match:
                amount = {'value': -match['usd_sent'], 'nok_value': -match['nok_received']}
                self.credit(match['date'], amount, transfer=True)
            else:
                unmatched.append(w)
                self.credit(w['date'], w['amount'], transfer=True)

            if 'fee' in w:
                self.credit(w['date'], w['fee'])

        if unmatched:
            logger.warning('Wire Transfer missing corresponding received record: %s', unmatched)
        return unmatched


    def process(self):
        # Process cash account
        total = 0
        posidx = 0
        total_received_price_nok = 0
        total_paid_price_nok = 0

        debit = [e for e in self.cash if e['amount']['value'] > 0]
        credit = [e for e in self.cash if e['amount']['value'] < 0]
        for e in credit:
            total += e['amount']['value']
            amount_to_sell = abs(e['amount']['value'])
            is_transfer = e['transfer']
            if is_transfer:
                total_received_price_nok += abs(e['amount']['nok_value'])
            while amount_to_sell > 0:
                if posidx >= len(debit):
                    raise Exception(f'Transferring more money that is in cash account {amount_to_sell}')
                amount = debit[posidx]['amount']['value']
                if amount == 0:
                    posidx += 1
                    continue
                if amount_to_sell >= amount:
                    if is_transfer:
                        total_paid_price_nok += debit[posidx]['amount']['nok_value']
                    amount_to_sell -= amount
                    debit[posidx]['amount'] = dict.fromkeys(debit[posidx]['amount'], 0)
                    posidx += 1
                else:
                    if is_transfer:
                        total_paid_price_nok += (amount_to_sell * debit[posidx]['amount']['nok_exchange_rate'])
                    debit[posidx]['amount']['value'] -= amount_to_sell
                    amount_to_sell = 0
                if posidx == len(debit):
                    break
        remaining_cash = [c for c in debit if c['amount']['value'] > 0]
        cash_report = {'total_purchased_nok': total_paid_price_nok,
                       'total_received_nok': total_received_price_nok, 'remaining_cash': remaining_cash,
                       'gain': total_received_price_nok - total_paid_price_nok}
        return cash_report
