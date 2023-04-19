'''
ESPPv2 Positions module
'''

#
# Remember to add the new tax-free deduction rates for a new year
#
tax_deduction_rates = {
    2006: [2.1, 3.0],
    2007: [3.3, 4.6],
    2008: [3.8, 5.2],
    2009: [1.3, 1.8],
    2010: [1.6, 2.2],
    2011: [1.5, 2.1],
    2012: [1.1, 1.6],
    2013: [1.1, 1.5],
    2014: [0.9, 1.2],
    2015: [0.6, 0.8],
    2016: [0.4, 0.5],
    2017: [0.7, 0.9],
    2018: [0.8, 1.1],
    2019: [1.3, 1.7],
    2020: [0.6, 0.8],
    2021: [0.5, 0.6],
    2022: [1.7, 2.1]
}

# pylint: disable=too-many-instance-attributes, line-too-long, invalid-name, logging-fstring-interpolation

import logging
from itertools import groupby
from copy import deepcopy
from datetime import datetime, date, timedelta
from math import isclose
from decimal import Decimal, getcontext
from espp2.fmv import FMV
from espp2.datamodels import *
from espp2.console import console

getcontext().prec = 6

logger = logging.getLogger(__name__)

f = FMV()

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
            if t.type in (EntryTypeEnum.DEPOSIT, EntryTypeEnum.BUY, EntryTypeEnum.SELL, EntryTypeEnum.TRANSFER):
                self.add(t.symbol, t.date, t.qty)

    def add(self, symbol, transactiondate, qty):
        '''Add entry to ledger'''
        if symbol not in self.entries:
            self.entries[symbol] = []
        total = sum(e[1] for e in self.entries[symbol])
        # assert total >= 0, f'Invalid total {total} for {symbol} on {transactiondate}'
        self.entries[symbol].append((transactiondate, qty, total+qty))

    def total_shares(self, symbol, untildate):
        '''Return total shares for symbol at end of day given by untildate'''
        last = 0

        if symbol not in self.entries:
            return 0
        for i, e in enumerate(self.entries[symbol]):
            if e[0] > untildate:
                return self.entries[symbol][i-1][2]
                # return e[2]
            last = e[2]
        return last


tax_deduction_rates = {year: Decimal(
    str(i[0])) for year, i in tax_deduction_rates.items()}

def get_tax_deduction_rate(year):
    '''Return tax deduction rate for year'''

    if year < 2006:
        logger.error('The tax deduction rate was introduced in 2006, no support for years prior to that. %s', year)
        return 0

    if year not in tax_deduction_rates:
        raise Exception(f'No tax deduction rate for year {year}')

    return tax_deduction_rates[year]
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

    def add_tax_deductions(self):
        '''Add tax deductions for the shares we hold end of year'''
        total_tax_deduction = 0
        end_of_year = f'{self.year}-12-31'
        for symbol in self.symbols:
            eoy_balance = self[:end_of_year, symbol]
            for item in eoy_balance:
                if item.qty == 0:
                    continue
                tax_deduction_rate = get_tax_deduction_rate(self.year)
                tax_deduction = (item.purchase_price.nok_value *
                                 tax_deduction_rate)/100
                self.tax_deduction[item.idx] += tax_deduction
                total_tax_deduction += (tax_deduction * item.qty)
        logger.info('Total tax deduction this year %s', total_tax_deduction)

    def __init__(self, year, opening_balance: Holdings, transactions, received_wires=None,
                 validate_year='exact', generate_holdings=False):
        # if validate_year == 'exact':
        #     transactions = [t for t in transactions if t.date.year == year]
        # elif validate_year == 'filter':
        #     transactions = [t for t in transactions if todate(
        #         t['date']).year <= year]
        # wrong_year = [t for t in transactions if t.date.year != year]
        # assert(len(wrong_year) == 0)
        self.year = year
        self.generate_holdings = generate_holdings
        # if not isinstance(cash, Cash):
        #     raise ValueError('Cash must be instance of Cash')

        self.new_holdings = [
            t for t in transactions if t.type in ('BUY', 'DEPOSIT')]
        # self._fixup_tax_deductions()
        if opening_balance:
            self.cash = Cash(year, opening_balance.cash,
                             generate_holdings=generate_holdings)
        else:
            self.cash = Cash(year, generate_holdings=generate_holdings)
        self.ledger = Ledger(opening_balance, transactions)
        if opening_balance and opening_balance.stocks:
            logger.info('Adding %d new holdings to %d previous holdings', len(
                self.new_holdings), len(opening_balance.stocks))
            logger.info(
                f'Previous holdings from: {opening_balance.year} {validate_year}')
            transactions = [t for t in transactions if t.date.year > opening_balance.year]
            self.new_holdings = [t for t in transactions if t.type in ('BUY', 'DEPOSIT')]
            self.positions = opening_balance.stocks + self.new_holdings
        else:
            if not generate_holdings:
                logger.warning(
                    "No previous holdings or stocks in holding file. Requires the complete transaction history.")
            self.positions = self.new_holdings

        if not generate_holdings:
            # Validate that all positions for the tax year has a valid purchase price.
            # A purchase price of zero indicates an auto-generated opening balance.
            zero_purchase_price = [p for p in self.positions if p.purchase_price.value == 0]
            assert len(
                zero_purchase_price) == 0, f'Found {len(zero_purchase_price)} positions with zero purchase price. {zero_purchase_price}'

        # Collect last years accumulated tax deduction
        total_accumulated_tax_deduction = 0
        self.tax_deduction = []
        for i, p in enumerate(self.positions):
            p.idx = i
            tax_deduction = p.dict().get('tax_deduction', 0)
            self.tax_deduction.insert(i, tax_deduction)
            total_accumulated_tax_deduction += (tax_deduction * p.qty)
        logger.info('Total tax deduction accumulated from previous years %s', total_accumulated_tax_deduction)

        self.positions_by_symbols = position_groupby(self.positions)

        self.new_holdings_by_symbols = position_groupby(self.new_holdings)
        self.symbols = self.positions_by_symbols.keys()

        # Sort sales
        sales = [t for t in transactions if t.type in ('SELL', 'TRANSFER')]
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
        self.taxsub_by_symbols = position_groupby(self.db_taxsub)

        # Wires
        self.db_wires = [t for t in transactions if t.type == 'WIRE']
        self.received_wires = received_wires

        # Fees
        self.db_fees = [t for t in transactions if t.type == 'FEE']

        # Cashadjusts
        self.db_cashadjusts = [t for t in transactions if t.type == 'CASHADJUST']

        # Add tax deduction to the positions we still hold at the end of the year
        self.add_tax_deductions()

        self.buys_report = None
        self.sales_report = None
        self.dividends_report = None
        self.cash_summary = None
        self.unmatched_wires_report = None
        self.fees_report = None

    def fundamentals(self) -> Dict[str, Fundamentals]:
        '''Return fundamentals for symbol at date'''
        r = {}
        for symbol in self.symbols:
            f = fmv.get_fundamentals(symbol)
            isin = f.get('General', {}).get('ISIN', None)
            if not isin:
                isin = f.get('ETF_Data', {}).get('ISIN', '')

            r[symbol] = Fundamentals(
                name=f['General']['Name'], isin=isin,
                country=f['General']['CountryName'], symbol=f['General']['Code'])
        return r

    def _balance(self, symbol, balancedate):
        '''
        Return posisions by a given date. Returns a view as a copy.
        If changes are required use the update() function.
        '''
        # Copy positions
        if symbol not in self.positions_by_symbols:
            return []
        posview = deepcopy(self.positions_by_symbols[symbol])
        posidx = 0
        if symbol in self.sale_by_symbols:
            for s in self.sale_by_symbols[symbol]:
                if s.date > balancedate:
                    # We are including positions sold on this day too.
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
            if i.date <= enddate:
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

    def _dividends(self):
        '''Process Dividends'''
        tax_deduction_used = 0
        # if not d.amount and not d.amount.ps:
        #     raise ValueError('Dividend amount is zero', d)


        # Deal with dividends and cash account
        for t in self.db_tax:
            self.cash.credit(t.date, t.amount, 'tax')
        for t in self.db_taxsub:
            self.cash.debit(t.date, t.amount, 'tax paid back')
        for i in self.db_dividend_reinv:
            self.cash.credit(i.date, i.amount, 'dividend reinvested')
        for t in self.db_cashadjusts:
            if t.amount.value > 0:
                self.cash.debit(t.date, t.amount, t.description)
            elif t.amount.value < 0:
                self.cash.credit(t.date, t.amount, t.description)

        r=[]
        norwegian_dividend_split = datetime(2022, 10, 5).date()
        for symbol, dividends in self.dividend_by_symbols.items():
            logger.debug('Processing dividends for %s', symbol)
            dividend_usd = 0 #sum(item.amount.value for item in dividends)
            dividend_nok = 0 #sum(item.amount.nok_value for item in dividends)
            if self.year == 2022:
                # Need to separately calculate pre and post tax increase for 2022.
                post_tax_inc_usd = sum(
                    item.amount.value for item in dividends if item.declarationdate > norwegian_dividend_split)
                post_tax_inc_nok = sum(
                    item.amount.nok_value for item in dividends if item.declarationdate > norwegian_dividend_split)
            else:
                post_tax_inc_usd = None
                post_tax_inc_nok = None
            # Note, in some cases taxes have not been withheld. E.g. dividends too small
            try:
                tax_usd = sum(item.amount.value for item in self.tax_by_symbols[symbol])
                tax_nok = sum(item.amount.nok_value for item in self.tax_by_symbols[symbol])
            except KeyError:
                tax_usd = tax_nok = 0
            for d in dividends:
                # To qualify for dividend, we need to have owned the stock the day before the exdate
                exdate = d.exdate - timedelta(days=1)
                total_shares = self.total_shares(self[:exdate, symbol])
                if self.ledger:
                    ledger_shares = self.ledger.total_shares(symbol, exdate)
                    assert isclose(total_shares, ledger_shares, abs_tol=10**-
                                   2), f"Total shares don't match {total_shares} (position balance) != {ledger_shares} (ledger) on {d.date} / {exdate}"
                if total_shares == 0:  # and not d.amount_ps:
                    if not self.generate_holdings:
                        raise InvalidPositionException(
                            f'Dividends: Total shares at dividend date is zero: {d}')
                    else:
                        logger.warning(
                            'Dividend for %s on %s has no shares', symbol, d.date)
                        continue
                if d.amount_ps:
                    # Inherit problem from pickle. Might not even have gotten dividends here.
                    dps = d.amount_ps.value
                    value = d.amount_ps * total_shares
                    d.amount = value
                else:
                    dps = d.amount.value / total_shares

                self.cash.debit(d.date, d.amount, 'dividend')
                dividend_usd += d.amount.value
                dividend_nok += d.amount.nok_value

                logger.info(
                    'Total shares of %s at dividend date: %s dps: %s reported: %s', symbol, total_shares, dps, d.dividend_dps)
                assert isclose(dps, d.dividend_dps, abs_tol=10**-2), f"Dividend for {exdate}/{d.date} per share calculated does not match reported {dps} vs {d.dividend_dps} for {total_shares} {d.amount.value}"
                for entry in self[:exdate, symbol]:  # Creates a view
                    entry.dps = dps if 'dps' not in entry else entry.dps + dps
                    dps_nok = dps * d.amount.nok_exchange_rate
                    tax_deduction = self.tax_deduction[entry.idx]
                    if tax_deduction > dps_nok:
                        tax_deduction_used += (dps_nok * entry.qty)
                        self.tax_deduction[entry.idx] -= dps_nok
                    elif tax_deduction > 0:
                        tax_deduction_used += (tax_deduction * entry.qty)
                        self.tax_deduction[entry.idx] = 0
                    self.update(entry.idx, 'dps', entry.dps)

            if symbol in self.taxsub_by_symbols:
                tax_returned = sum(item.amount.value for item in self.taxsub_by_symbols[symbol])
            else:
                tax_returned = 0
            if tax_returned:
                exchange_rate = tax_nok / tax_usd
                tax_usd += tax_returned
                assert abs(tax_usd) > 0, f"Dividend tax after tax return is negative {tax_usd}"
                tax_nok = tax_usd * exchange_rate

            if post_tax_inc_usd:
                r.append(EOYDividend(symbol=symbol,
                                    amount=Amount(currency="USD",
                                                value=dividend_usd,
                                                nok_value=dividend_nok-tax_deduction_used,
                                                nok_exchange_rate=0),
                                    gross_amount=Amount(currency="USD",
                                                value=dividend_usd,
                                                nok_value=dividend_nok,
                                                nok_exchange_rate=0),
                                    post_tax_inc_amount=Amount(currency="USD",
                                                            value=post_tax_inc_usd,
                                                            nok_value=post_tax_inc_nok,
                                                            nok_exchange_rate=0),
                                    tax=Amount(currency="USD",
                                                value=tax_usd,
                                                nok_value=tax_nok,
                                                nok_exchange_rate=0),
                                    tax_deduction_used=tax_deduction_used))
            else:
                r.append(EOYDividend(symbol=symbol,
                                    amount=Amount(currency="USD",
                                                value=dividend_usd,
                                                nok_value=dividend_nok-tax_deduction_used,
                                                nok_exchange_rate=0),
                                    gross_amount=Amount(currency="USD",
                                                value=dividend_usd,
                                                nok_value=dividend_nok,
                                                nok_exchange_rate=0),
                                    tax=Amount(currency="USD",
                                                value=tax_usd,
                                                nok_value=tax_nok,
                                                nok_exchange_rate=0),
                                    tax_deduction_used=tax_deduction_used))
        return r

    def dividends(self):
        '''Calculate dividends for the year.'''
        if not self.dividends_report:
            self.dividends_report = self._dividends()
        return self.dividends_report

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
            if s.fee and s.fee.value < 0:
                self.cash.credit(s.date, s.fee.copy(), 'sale fee')
            # Distinguish between real sale and a transfer
            is_sale = s.type == EntryTypeEnum.SELL
            if is_sale:
                s_record = EOYSales(date=s.date, symbol=symbol, qty=s.qty,
                            fee=s.fee, amount=s.amount, from_positions=[])
                self.cash.debit(s.date, s.amount.copy(), 'sale')

            qty_to_sell = abs(s.qty)
            while qty_to_sell > 0:
                if positions[posidx].qty == 0:
                    posidx += 1
                if qty_to_sell >= positions[posidx].qty:
                    if is_sale:
                        r = self.individual_sale(
                            s, positions[posidx], positions[posidx].qty)
                    qty_to_sell -= positions[posidx].qty
                    positions[posidx].qty = 0
                    posidx += 1
                else:
                    if is_sale:
                        r = self.individual_sale(s, positions[posidx], qty_to_sell)
                    positions[posidx].qty -= qty_to_sell
                    qty_to_sell = 0
                if is_sale:
                    s_record.from_positions.append(r)
            if not is_sale:
                continue

            total_gain = sum(item.gain_ps * item.qty
                             for item in s_record.from_positions)
            if self.year == 2022:
                total_gain_post_tax_inc = sum(item.gain_ps * item.qty
                                             for item in s_record.from_positions if s_record.date > date(2022, 10, 5))
                if not total_gain_post_tax_inc:
                    total_gain_post_tax_inc = Amount(0)
            else:
                total_gain_post_tax_inc = Amount(0)
            total_tax_ded = sum(item.tax_deduction_used * item.qty
                                for item in s_record.from_positions)
            total_purchase_price = sum(
                item.purchase_price * item.qty for item in s_record.from_positions)
            if s.fee:
                total_purchase_price += s.fee
            totals = {'gain': total_gain,
                      'post_tax_inc_gain': total_gain_post_tax_inc,
                      'purchase_price': total_purchase_price,
                      'tax_ded_used': total_tax_ded,
                      }
            s_record.totals = totals
            sales_report.append(s_record)

        return sales_report

    def _sales(self):
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

    def sales(self):
        '''Return report of sales'''
        if not self.sales_report:
            self.sales_report = self._sales()
        return self.sales_report

    def _fees(self):
        for f in self.db_fees:
            self.cash.credit(f.date, f.amount, 'fee')
    def fees(self):
        if not self.fees_report:
            self.fees_report = self._fees()
        return self.fees_report

    def _buys(self):
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
                        self.cash.credit(item['date'], item['amount'], 'buy')
                    else:
                        amount = Amount(value=-item.purchase_price.value * item.qty, currency=item.purchase_price.currency,
                                        nok_exchange_rate=item.purchase_price.nok_exchange_rate,
                                        nok_value=-item.purchase_price.nok_value * item.qty)
                        self.cash.credit(item.date, amount, 'buy')
                bought += item.qty
                price_sum += item.purchase_price.value
                price_sum_nok += item.purchase_price.nok_value
            avg_usd = price_sum/len(self.new_holdings_by_symbols[symbol])
            avg_nok = price_sum_nok/len(self.new_holdings_by_symbols[symbol])
            r.append({'symbol': symbol, 'qty': bought,
                     'avg_usd': avg_usd, 'avg_nok': avg_nok})
        return r

    def buys(self):
        if self.buys_report:
            return self.buys_report
        self.buys_report = self._buys()
        return self.buys_report

    def eoy_balance(self, year):
        '''End of year summary of holdings'''
        end_of_year = f'{year}-12-31'

        eoy_exchange_rate = f.get_currency('USD', end_of_year)
        r = []
        for symbol in self.symbols:
            eoy_balance = self[:end_of_year, symbol]
            total_shares = self.total_shares(eoy_balance)
            eoyfmv = f[symbol, end_of_year]

            r.append(EOYBalanceItem(symbol=symbol, qty=total_shares, amount=Amount(
                value=total_shares * eoyfmv, currency='USD',
                nok_exchange_rate=eoy_exchange_rate,
                nok_value=total_shares * eoyfmv * eoy_exchange_rate),
                fmv=eoyfmv))
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
                # tax_deduction = self.tax_deduction[item.idx]
                # tax_deduction_rate = get_tax_deduction_rate(year)
                # tax_deduction += (item.purchase_price.nok_value *
                #                   tax_deduction_rate)/100
                hitem = Stock(date=item.date, symbol=item.symbol, qty=item.qty,
                              purchase_price=item.purchase_price.copy(), tax_deduction=self.tax_deduction[item.idx])
                stocks.append(hitem)
        return Holdings(year=year, broker=broker, stocks=stocks, cash=self.cash_summary.holdings)

    def process(self):
        '''Process all transactions'''
        self.buys()
        self.sales()
        self.dividends()
        self.fees()

        # Process wires
        self.unmatched_wires_report = self.cash.wire(self.db_wires, self.received_wires)
        # print('unmatched', unmatched)
        try:
            self.cash_summary = self.cash.process()
        except CashException as e:
            l = self.cash.ledger()
            s = ''
            for entry in l:
                s += f'{entry[0].date} {entry[0].amount.value} {entry[0].description} {entry[1]}\n'
            # raise CashException(f'{str(e)}:\n{s}')
            pass


class Cash():
    '''Cash balance'''
    def __init__(self, year, opening_balance=[], generate_holdings=False):
        '''Initialize cash balance for a given year.'''
        self.year = year
        self.cash = CashModel().cash
        self.generate_holdings = generate_holdings

        # Spin through and add the opening balance
        for e in opening_balance:
            self.cash.append(e)

    def sort(self):
        '''Sort cash entries by date'''
        self.cash = sorted(self.cash, key=lambda d: d.date)

    def debit(self, debitdate, amount, description=''):
        '''Debit cash balance'''
        logger.debug('Cash debit: %s: %s', debitdate, amount.value)
        if amount.value < 0:
            raise ValueError('Amount must be positive')
        self.cash.append(CashEntry(date=debitdate, amount=amount, description=description))
        self.sort()

    def credit(self, creditdate, amount, description='', transfer=False):
        ''' TODO: Return usdnok rate for the item credited '''
        logger.debug('Cash credit: %s: %s', creditdate, amount.value)
        if amount.value > 0:
            raise ValueError(f'Amount must be negative {amount}')

        self.cash.append(
            CashEntry(date=creditdate, amount=amount, description=description, transfer=transfer))
        self.sort()

    def _wire_match(self, wire, wires_received):
        '''Match wire transfer to received record'''
        if isinstance(wires_received, list) and len(wires_received) == 0:
            return None
        try:
            for v in wires_received.__root__:
                if v.date == wire.date and isclose(v.value, abs(wire.amount.value), abs_tol=0.05):
                    return v
        except AttributeError as e:
            logger.error(f'No received wires processing failed {wire}')
            raise ValueError(f'No received wires processing failed {wire}') from e
        return None

    def ledger(self):
        '''Cash ledger'''
        total = 0
        ledger = []
        for c in self.cash:
            total += c.amount.value
            ledger.append((c, total))
        return ledger

    def wire(self, wire_transactions, wires_received):
        '''Process wires from sent and received (manual) records'''
        unmatched = []

        for w in wire_transactions:
            match = self._wire_match(w, wires_received)
            if match:
                nok_exchange_rate = match.nok_value/match.value
                amount = Amount(currency=match.currency, value=-match.value,
                                nok_value=-match.nok_value, nok_exchange_rate=nok_exchange_rate)
                self.credit(match.date, amount, 'wire', transfer=True)
            else:
                # TODO: What's the exchange rate here?
                # Should be NaN?
                unmatched.append(WireAmount(date=w.date, currency=w.amount.currency, nok_value=w.amount.nok_value, value=w.amount.value))
                self.credit(w.date, w.amount, 'wire', transfer=True)
            if w.fee:
                self.credit(w.date, w.fee, 'wire fee')

        if unmatched and not self.generate_holdings:
            logger.warning(
                'Wire Transfer missing corresponding received record: %s', unmatched)
        return unmatched

    def process(self):
        '''Process cash account'''
        cash_positions = deepcopy(self.cash)
        posidx = 0
        debit = [e for e in cash_positions if e.amount.value > 0]
        credit = [e for e in cash_positions if e.amount.value < 0]
        transfers = []
        for e in credit:
            total_received_price_nok = 0
            total_paid_price_nok = 0
            total = e.amount.value
            amount_to_sell = abs(e.amount.value)
            is_transfer = e.transfer
            if is_transfer:
                total_received_price_nok += abs(e.amount.nok_value)
            while amount_to_sell > 0 and posidx < len(debit):
                amount = debit[posidx].amount.value
                if amount == 0:
                    posidx += 1
                    continue
                if amount_to_sell >= amount:
                    if is_transfer:
                        total_paid_price_nok += (debit[posidx].amount.value * debit[posidx].amount.nok_exchange_rate)
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

            # if amount_to_sell > 0:
            #     raise CashException(
            #         f'Transferring more money that is in cash account {amount_to_sell} {e}')

            # Only care about tranfers
            if is_transfer:
                transfers.append(TransferRecord(date=e.date,
                                                amount_sent=round(total_paid_price_nok),
                                                amount_received=round(total_received_price_nok),
                                                description=e.description,
                                 gain=round(total_received_price_nok - total_paid_price_nok)))
        remaining_usd = sum([c.amount.value for c in debit if c.amount.value > 0])
        eoy = datetime(self.year, 12, 31)
        exchange_rate = f.get_currency('USD', eoy)
        remaining_nok = remaining_usd * exchange_rate
        remaining_cash = Amount(value=remaining_usd, currency='USD',
                                nok_value=remaining_nok, nok_exchange_rate=exchange_rate)
        total_gain = sum([t.gain for t in transfers])
        total_paid_price_nok = sum([t.amount_sent for t in transfers])
        total_received_price_nok = sum([t.amount_received for t in transfers])

        # Cash holdings. List of WireAmounts
        cash_holdings = []
        for e in debit:
            if e.amount.value > 0:
                e.amount.nok_value = e.amount.value * e.amount.nok_exchange_rate # Reset this after selling
                cash_holdings.append(CashEntry(date=e.date,
                                                description=e.description,
                                                amount=e.amount))
        return CashSummary(transfers=transfers, remaining_cash=remaining_cash, gain=total_gain, holdings=cash_holdings)
