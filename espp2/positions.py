'''
ESPPv2 Positions module
'''

# pylint: disable=too-many-instance-attributes, line-too-long, invalid-name, logging-fstring-interpolation

import logging
from itertools import groupby
from copy import deepcopy
from datetime import datetime, date
from math import isclose
from decimal import Decimal, getcontext
from espp2.fmv import FMV
from espp2.datamodels import *

getcontext().prec = 6

logger = logging.getLogger(__name__)


class InvalidPositionException(Exception):
    '''Invalid position'''


class CashException(Exception):
    '''Cash exception'''


def position_groupby(data):
    '''Group data by symbol'''
    sorted_data = sorted(data, key=lambda x: x.symbol)
    by_symbols = {}
    for k, g in groupby(sorted_data, key=lambda x: x.symbol):
        by_symbols[k] = list(g)
    return by_symbols


def todate(datestr: str) -> date:
    '''Convert string to datetime'''
    return datetime.strptime(datestr, '%Y-%m-%d').date()

class Ledger():
    '''Ledger of transactions and holdings'''
    def __init__(self, holdings, transactions):
        self.entries = {}
        if holdings:
            h = holdings.stocks
            for e in h:
                e.type = EntryTypeEnum.DEPOSIT
            transactions = [t for t in transactions if t.date.year > holdings.year]
        else:
            h = []
        transactions_sorted = sorted(transactions + h, key=lambda d: d.date)

        for t in transactions_sorted:
            if t.type in (EntryTypeEnum.DEPOSIT, EntryTypeEnum.BUY, EntryTypeEnum.SELL):
                self.add(t.symbol, t.date, t.qty)

    def add(self, symbol, date, qty):
        '''Add entry to ledger'''
        if symbol not in self.entries:
            self.entries[symbol] = []
        total = sum(e[1] for e in self.entries[symbol])
        self.entries[symbol].append((date, qty, total+qty))

    def total_shares(self, symbol, date, until=True):
        '''Return total shares for symbol at date'''
        last = 0
        if symbol not in self.entries:
            return 0
        for i, e in enumerate(self.entries[symbol]):
            if e[0] >= date:
                if until:
                    return self.entries[symbol][i-1][2]
                return e[2]
            last = e[2]
        return last

class Positions():
    '''
    Keep track of stock positions. Expect transactions for this year and holdings from previous year.
    '''

    def _fixup_tax_deductions(self):
        '''ESPP purchased last year but accounted this year deserves tax deduction'''
        for p in self.new_holdings:
            if p.type == 'DEPOSIT' and p.description == 'ESPP':
                if p.date.year - 1 == p.purchase_date.year:
                    year = p.purchase_date.year
                    p.tax_deduction = (self.tax_deduction_rate[str(
                        year)] * p.purchase_price.nok_value)/100
                    logger.debug(
                        'Adding tax deduction for ESPP from last year %s', p)

    def __init__(self, year, taxdata, prev_holdings: Holdings, transactions, cash, validate_year='exact', ledger=None):
        # if validate_year == 'exact':
        #     transactions = [t for t in transactions if t.date.year == year]
        # elif validate_year == 'filter':
        #     transactions = [t for t in transactions if todate(
        #         t['date']).year <= year]
        # wrong_year = [t for t in transactions if t.date.year != year]
        # assert(len(wrong_year) == 0)

        self.tax_deduction_rate = {year: Decimal(
            str(i[0])) for year, i in taxdata['tax_deduction_rates'].items()}
        self.new_holdings = [
            t for t in transactions if t.type in ('BUY', 'DEPOSIT')]
        self._fixup_tax_deductions()
        self.cash = cash
        self.ledger = ledger
        if prev_holdings and prev_holdings.stocks:
            logger.info('Adding %d new holdings to %d previous holdings', len(
                self.new_holdings), len(prev_holdings.stocks))
            logger.info(
                f'Previous holdings from: {prev_holdings.year} {validate_year}')
            transactions = [t for t in transactions if t.date.year > prev_holdings.year]
            self.new_holdings = [t for t in transactions if t.type in ('BUY', 'DEPOSIT')]
            self.positions = prev_holdings.stocks + self.new_holdings
        else:
            logger.warning(
                "No previous holdings or stocks in holding file. Requires the complete transaction history.")
            self.positions = self.new_holdings
        self.tax_deduction = []
        for i, p in enumerate(self.positions):
            p.idx = i
            tax_deduction = p.dict().get('tax_deduction', 0)
            self.tax_deduction.insert(i, tax_deduction)

        self.positions_by_symbols = position_groupby(self.positions)

        self.new_holdings_by_symbols = position_groupby(self.new_holdings)
        self.symbols = self.positions_by_symbols.keys()

        # Sort sales
        sales = [t for t in transactions if t.type == 'SELL']
        self.sale_by_symbols = position_groupby(sales)

        # Dividends
        self.db_dividends = [t for t in transactions if t.type == 'DIVIDEND']
        self.dividend_by_symbols = position_groupby(self.db_dividends)

        self.db_dividend_reinv = [
            t for t in transactions if t.type == 'DIVIDEND_REINV']
        self.dividend_reinv_by_symbols = position_groupby(
            self.db_dividend_reinv)

        # Tax
        self.db_tax = [t for t in transactions if t.type == 'TAX']
        self.db_taxsub = [t for t in transactions if t.type == 'TAXSUB']
        self.tax_by_symbols = position_groupby(self.db_tax)
        # cls.tax_deduction_rate = taxdata['tax_deduction_rates']

        # # Wires
        # cls.db_wires = [t for t in transactions if t['type'] == 'WIRE']

    def _balance(self, symbol, balancedate):
        '''
        Return posisions by a given date. Returns a view as a copy.
        If changes are required use the update() function.
        '''
        # Copy positions
        posview = deepcopy(self.positions_by_symbols[symbol])
        posidx = 0
        if symbol in self.sale_by_symbols:
            for s in self.sale_by_symbols[symbol]:
                if s.date > balancedate:
                    break
                if posview[posidx].date > balancedate:
                    raise InvalidPositionException(
                        f'Trying to sell stock from the future {posview[posidx].date} > {balancedate}')
                qty_to_sell = s.qty.copy_abs()
                assert qty_to_sell > 0
                while qty_to_sell > 0:
                    if posidx >= len(posview):
                        raise InvalidPositionException(
                            'Selling more shares than we hold', s, posview)
                    if posview[posidx].qty == 0:
                        posidx += 1
                    if qty_to_sell >= posview[posidx].qty:
                        qty_to_sell -= posview[posidx].qty
                        posview[posidx].qty = 0
                        posidx += 1
                    else:
                        posview[posidx].qty -= qty_to_sell
                        qty_to_sell = 0
        return posview

    def __getitem__(self, val):
        '''
        Index 0: date slice
        Index 1: symbol
        '''
        enddate = todate(val[0].stop) if isinstance(
            val[0].stop, str) else val[0].stop
        b = self._balance(val[1], enddate)
        for i in b:
            if i.date < enddate:
                yield i
            else:
                break

    def update(self, index, fieldname, value):
        '''Update a field in a position'''
        logger.debug('Entry update: %s %s %s', index, fieldname, value)
        self.positions[index].fieldname = value

    def total_shares(self, balanceiter):
        '''Returns total number of shares given an iterator (from __getitem__)'''
        total = Decimal(0)
        for i in balanceiter:
            total += i.qty
        return total

    def dividends(self):
        '''Process Dividends'''
        tax_deduction_used = 0

        # Deal with dividends and cash account
        for d in self.db_dividends:
            self.cash.debit(d.date, d.amount)
        for t in self.db_tax:
            self.cash.credit(t.date, t.amount)
        for t in self.db_taxsub:
            self.cash.debit(t.date, t.amount)
        for i in self.db_dividend_reinv:
            self.cash.credit(i.date, i.amount)

        r=[]
        for symbol, dividends in self.dividend_by_symbols.items():
            logger.debug('Processing dividends for %s', symbol)
            dividend_usd = sum(item.amount.value for item in dividends)
            dividend_nok = sum(item.amount.nok_value for item in dividends)
            # Note, in some cases taxes have not been withheld. E.g. dividends too small
            try:
                tax_usd = sum(item.amount.value for item in self.tax_by_symbols[symbol])
                tax_nok = sum(item.amount.nok_value for item in self.tax_by_symbols[symbol])
            except KeyError:
                tax_usd = tax_nok = 0
            for d in dividends:
                total_shares = self.total_shares(self[:d.date, symbol])
                ledger_shares = self.ledger.total_shares(symbol, d.date)
                assert isclose(total_shares, ledger_shares, abs_tol=10**-2 ), f"Total shares don't match {total_shares} != {ledger_shares}"
                if total_shares == 0:
                    raise InvalidPositionException(
                        f'Dividends: Total shares at dividend date is zero: {d}')
                dps = d.amount.value / total_shares
                for entry in self[:d.date, symbol]:  # Creates a view
                    entry.dps = dps if 'dps' not in entry else entry.dps + dps
                    tax_deduction = self.tax_deduction[entry.idx]
                    if tax_deduction > entry.dps:
                        tax_deduction_used += (entry.dps * entry.qty)
                        self.tax_deduction[entry.idx] -= entry.dps
                    elif tax_deduction > 0:
                        tax_deduction_used += (tax_deduction * entry.qty)
                        self.tax_deduction[entry.idx] = 0
                    self.update(entry.idx, 'dps', entry.dps)
            r.append(EOYDividend(symbol=symbol,
                                 amount=Amount(currency="USD",
                                               value=dividend_usd,
                                               nok_value=dividend_nok,
                                               nok_exchange_rate=0),
                                 tax=Amount(currency="USD",
                                            value=tax_usd,
                                            nok_value=tax_nok,
                                            nok_exchange_rate=0),
                                 tax_deduction_used=tax_deduction_used))
        return r

    def individual_sale(self, sale_entry, buy_entry, qty):
        '''Calculate gain. Currently using total amount that includes fees.'''
        sale_price = sale_entry.amount.value / abs(sale_entry.qty)
        sale_price_nok = sale_price * sale_entry.amount.nok_exchange_rate
        gain = sale_price_nok - buy_entry.purchase_price.nok_value
        gain_usd = sale_price - buy_entry.purchase_price.value
        tax_deduction_used = 0
        tax_deduction = self.tax_deduction[buy_entry.idx]
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

        return SalesPosition(symbol=buy_entry.symbol,
                             qty=qty,
                             purchase_date=buy_entry.date,
                             sale_price=Amount(currency="USD",
                                               value=sale_price,
                                               nok_value=sale_price_nok,
                                               nok_exchange_rate=sale_entry.amount.nok_exchange_rate),
                             purchase_price=buy_entry.purchase_price,
                             gain_ps=Amount(currency="USD",
                                            value=gain_usd,
                                            nok_value=gain,
                                            nok_exchange_rate=1),
                             tax_deduction_used=tax_deduction_used,
                             )

    def process_sale_for_symbol(self, symbol, sales, positions):
        '''Process sales for a symbol'''
        posidx = 0
        sales_report = []

        for s in sales:
            s_record = EOYSales(date=s.date, symbol=symbol, qty=s.qty,
                        fee=s.fee, amount=s.amount, from_positions=[])
            qty_to_sell = abs(s.qty)
            self.cash.debit(s.date, s.amount.copy())
            while qty_to_sell > 0:
                if positions[posidx].qty == 0:
                    posidx += 1
                if qty_to_sell >= positions[posidx].qty:
                    r = self.individual_sale(
                        s, positions[posidx], positions[posidx].qty)
                    qty_to_sell -= positions[posidx].qty
                    positions[posidx].qty = 0
                    posidx += 1
                else:
                    r = self.individual_sale(s, positions[posidx], qty_to_sell)
                    positions[posidx].qty -= qty_to_sell
                    qty_to_sell = 0
                s_record.from_positions.append(r)

            total_gain = sum(item.gain_ps * item.qty
                             for item in s_record.from_positions)
            total_tax_ded = sum(item.tax_deduction_used
                                for item in s_record.from_positions)
            total_purchase_price = sum(
                item.purchase_price * item.qty for item in s_record.from_positions)
            if s.fee:
                total_purchase_price += s.fee
            totals = {'gain': total_gain, 'purchase_price': total_purchase_price, 'tax_ded_used': total_tax_ded,
                      }
            s_record.totals = totals
            sales_report.append(s_record)

        return sales_report

    def sales(self):
        '''Process all sales.'''

        # Walk through all sales from transactions. Deducting from balance.
        sale_report = {}
        for symbol, record in self.sale_by_symbols.items():
            # totals = {}
            positions = deepcopy(self.positions_by_symbols[symbol])
            r = self.process_sale_for_symbol(symbol, record, positions)
            if symbol not in sale_report:
                sale_report[symbol] = []
            sale_report[symbol] += r
        return sale_report

    def buys(self):
        '''Return report of BUYS'''
        r = []
        for symbol in self.symbols:
            bought = 0
            price_sum = 0
            price_sum_nok = 0
            if symbol not in self.new_holdings_by_symbols:
                continue
            for item in self.new_holdings_by_symbols[symbol]:
                if item.type == 'BUY':
                    if 'amount' in item:
                        self.cash.credit(item['date'], item['amount'])
                    else:
                        amount = Amount(value=item.purchase_price.value * item.qty, currency=item.purchase_price.currency,
                                        nok_exchange_rate=item.purchase_price.nok_exchange_rate,
                                        nok_value=item.purchase_price.nok_value * item.qty)
                        self.cash.credit(item.date, amount)
                bought += item.qty
                price_sum += item.purchase_price.value
                price_sum_nok += item.purchase_price.nok_value
            avg_usd = price_sum/len(self.new_holdings_by_symbols[symbol])
            avg_nok = price_sum_nok/len(self.new_holdings_by_symbols[symbol])
            r.append({'symbol': symbol, 'qty': bought,
                     'avg_usd': avg_usd, 'avg_nok': avg_nok})
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

            r.append(EOYBalanceItem(symbol=symbol, qty=total_shares, amount=Amount(
                value=total_shares * fmv, currency='USD', 
                nok_exchange_rate=eoy_exchange_rate, 
                nok_value=total_shares * fmv * eoy_exchange_rate),
                fmv=fmv))
        return r

    def holdings(self, year, broker):
        '''End of year positions in ESPP holdings format'''
        end_of_year = f'{year}-12-31'
        stocks = []
        for symbol in self.symbols:
            eoy_balance = self[:end_of_year, symbol]
            for item in eoy_balance:
                if item.qty == 0:
                    continue
                tax_deduction = self.tax_deduction[item.idx]
                tax_deduction += (item.purchase_price.nok_value *
                                  self.tax_deduction_rate[str(year)])/100
                hitem = Stock(date=item.date, symbol=item.symbol, qty=item.qty,
                              purchase_price=item.purchase_price.copy(), tax_deduction=tax_deduction)
                stocks.append(hitem)
        return Holdings(year=year, broker=broker, stocks=stocks, cash=[])


class Cash():
    ''' Cash balance.
    1) Cash USD Brokerage (per valuta)
    2) Hjemmebeholdning av valuta  (valutatrans)
    3) NOK hjemme
    '''

    def __init__(self, year, transactions=None, wires=None):
        transactions = [t for t in transactions if t.date.year == year]

        # Put any initialization here.
        self.db_wires = [t for t in transactions if t.type == 'WIRE']
        self.db_received = wires
        self.cash = CashModel().cash

    def sort(self):
        '''Sort cash entries by date'''
        self.cash = sorted(self.cash, key=lambda d: d.date)

    def debit(self, debitdate, amount,):
        '''Debit cash balance'''
        logger.debug('Cash debit: %s: %s', debitdate, amount.value)
        self.cash.append(CashEntry(date=debitdate, amount=amount))
        self.sort()

    def credit(self, creditdate, amount, transfer=False):
        ''' TODO: Return usdnok rate for the item credited '''
        logger.debug('Cash credit: %s: %s', creditdate, amount.value)
        self.cash.append(
            CashEntry(date=creditdate, amount=amount, transfer=transfer))
        self.sort()

    def _wire_match(self, wire):
        '''Match wire transfer to received record'''
        if isinstance(self.db_received, list) and len(self.db_received) == 0:
            return None
        try:
            for v in self.db_received.wires:
                if v.date == wire.date and isclose(v.wire.value, abs(wire.amount.value), abs_tol=0.05):
                    return v
        except AttributeError:
            logger.error(f'No received wires processing failed {v}, {wire}')
            raise
        return None

    def wire(self):
        '''Process wires from sent and received (manual) records'''
        unmatched = []

        for w in self.db_wires:
            match = self._wire_match(w)
            if match:
                nok_exchange_rate = match.wire.nok_value/match.wire.value
                amount = Amount(currency=match.wire.currency, value=-match.wire.value,
                                nok_value=-match.wire.nok_value, nok_exchange_rate=nok_exchange_rate)
                self.credit(match.date, amount, transfer=True)
            else:
                unmatched.append(w)
                self.credit(w.date, w.amount, transfer=True)

            if 'fee' in w:
                self.credit(w['date'], w['fee'])

        if unmatched:
            logger.warning(
                'Wire Transfer missing corresponding received record: %s', unmatched)
        return unmatched

    def process(self):
        '''Process cash account'''
        total = 0
        posidx = 0
        total_received_price_nok = 0
        total_paid_price_nok = 0
        debit = [e for e in self.cash if e.amount.value > 0]
        credit = [e for e in self.cash if e.amount.value < 0]

        for e in credit:
            total += e.amount.value
            amount_to_sell = abs(e.amount.value)
            is_transfer = e.transfer
            if is_transfer:
                total_received_price_nok += abs(e.amount.nok_value)
            while amount_to_sell > 0:
                if posidx >= len(debit):
                    raise CashException(
                        f'Transferring more money that is in cash account {amount_to_sell}')
                amount = debit[posidx].amount.value
                if amount == 0:
                    posidx += 1
                    continue
                if amount_to_sell >= amount:
                    if is_transfer:
                        total_paid_price_nok += debit[posidx].amount.nok_value
                    amount_to_sell -= amount
                    # Clear the amount??
                    # Amount(**dict.fromkeys(debit[posidx].amount, 0))
                    debit[posidx].amount.value = 0
                    posidx += 1
                else:
                    if is_transfer:
                        total_paid_price_nok += (amount_to_sell *
                                                 debit[posidx].amount.nok_exchange_rate)
                    debit[posidx].amount.value -= amount_to_sell
                    amount_to_sell = 0
                if posidx == len(debit):
                    break
        remaining_cash = [c for c in debit if c.amount.value > 0]
        # TODO: Use data model
        cash_report = {'total_purchased_nok': total_paid_price_nok,
                       'total_received_nok': total_received_price_nok, 'remaining_cash': remaining_cash,
                       'gain': total_received_price_nok - total_paid_price_nok}
        return cash_report
