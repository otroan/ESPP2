'''
Morgan Stanley HTML table transaction history normalizer.
'''

# pylint: disable=invalid-name
# pylint: disable=no-name-in-module
# pylint: disable=no-self-argument

import math
from decimal import Decimal
import html5lib
from pydantic import parse_obj_as
from espp2.fmv import FMV
from espp2.datamodels import Transactions, Entry, EntryTypeEnum, Amount
import re
import logging
from pandas import MultiIndex, Index

logger = logging.getLogger(__name__)
currency_converter = FMV()

def setitem(rec, name, val):
    '''Used to set cell-values from a table by to_dict() function'''
    if val is None:
        return
    if isinstance(val, float):
        if math.isnan(val):
            return
        rec[name] = Decimal(f'{val}')
        return
    if not isinstance(val, str):
        raise ValueError(f'setitem() expected string, got {val}')
    rec[name] = val

class Table:
    def __init__(self, tablenode, idx):
        self.tablenode = tablenode
        self.data = decode_data(tablenode)
        self.colnames = []
        self.colname2idx = dict()
        self.header = []
        self.rows = []
        self.idx = idx

    def get(self, row, colname):
        try:
            idx = self.colname2idx[colname]
        except KeyError:
            return None
        if idx >= len(row):
            return None
        return row[idx]

    def to_dict(self):
        rc = []
        for row in self.rows:
            rec = dict()
            for colname in self.colname2idx.keys():
                setitem(rec, colname, self.get(row, colname))
            rc.append(rec)
        return rc

class ParseState:
    def __init__(self, filename):
        self.source = f'morgan:{filename}'
        self.transactions = []
        self.activity = '<unknown>'
        self.symbol = None
        self.entry_date = None
        self.date2dividend = dict()

    def parse_activity(self, row):
        '''Parse the "Activity" column'''
        self.activity = getitem(row, 'Activity')

    def parse_entry_date(self, row):
        '''Parse the "Entry Date" date, common to many tables'''
        date = getitem(row, 'Entry Date')
        if date is None:
            raise ValueError(f'Entry-date is not provided for {row}')
        self.entry_date = fixup_date(date)

    def parse_fund_symbol(self, row, column):
        '''Parse the "Fund: CSCO - NASDAQ" type headers'''
        item, ok = getitems(row, column)
        if ok:
            m = re.match(r'''^Fund:\s+([A-Za-z]+)\s''', item)
            if m:
                self.symbol = m.group(1)
                if self.symbol == 'Cash':
                    self.symbol = None
                return True    # No more parsing needed
        return False

    def deposit(self, qty, purchase_price, description, purchase_date=None):
        assert self.symbol is not None

        r = { 'type': EntryTypeEnum.DEPOSIT,
              'date': self.entry_date,
              'qty': qty,
              'symbol': self.symbol,
              'description': description,
              'purchase_price': purchase_price,
              'purchase_date': purchase_date,
              'source': self.source,
              'broker': 'morgan' }

        self.transactions.append(parse_obj_as(Entry, r))

    def sell(self, qty, price):
        assert self.symbol is not None

        r = { 'type': EntryTypeEnum.SELL,
              'date': self.entry_date,
              'qty': qty,
              'amount': fixup_price(self.entry_date, 'USD', f'{price * -qty}'),
              'symbol': self.symbol,
              'description': self.activity,
              'source': self.source }

        self.transactions.append(parse_obj_as(Entry, r))

    def dividend(self, amount):
        assert self.symbol is not None

        date = self.entry_date

        r = { 'type': EntryTypeEnum.DIVIDEND,
              'date': date,
              'symbol': self.symbol,
              'amount': amount,
              'source': self.source,
              'description': 'Credit' }

        if date in self.date2dividend:
            rr = self.date2dividend[date]
            assert(r['amount']['nok_exchange_rate'] == rr.amount.nok_exchange_rate)
            rr.amount.value += r['amount']['value']
            rr.amount.nok_value += r['amount']['nok_value']
            print(f"### DIV: {date} +{r['amount']['value']} (Again)")
            return

        print(f"### DIV: {date} +{r['amount']['value']} (First)")
        self.date2dividend[date] = parse_obj_as(Entry, r)

    def flush_dividend(self):
        for date in self.date2dividend.keys():
            self.transactions.append(self.date2dividend[date])

    def dividend_reinvest(self, amount):
        assert self.symbol is not None

        r = { 'type': EntryTypeEnum.DIVIDEND_REINV,
              'date': self.entry_date,
              'symbol': self.symbol,
              'amount': amount,
              'source': self.source,
              'description': 'Debit' }

        self.transactions.append(parse_obj_as(Entry, r))

    def wire_transfer(self, date, amount, fee):
        assert self.symbol is not None

        r = { 'type': EntryTypeEnum.WIRE,
              'date': date,
              'amount': amount,
              'description': 'Cash Disbursement',
              'fee': fee,
              'source': self.source }

        self.transactions.append(parse_obj_as(Entry, r))

    def cashadjust(self, date, amount, description):
        '''Ad-hoc cash-adjustment (positive or negative)'''
        r = { 'type': EntryTypeEnum.CASHADJUST,
              'date': date,
              'amount': amount,
              'description': description,
              'source': self.source }

        self.transactions.append(parse_obj_as(Entry, r))

    def parse_rsu_release(self, row):
        '''Handle what appears to be RSUs added to account'''
        m = re.match(r'''^Release\s+\(([A-Z0-9]+)\)''', self.activity)
        if not m:
            return False

        id = m.group(1)     # Unused for now
        qty, value, ok = getitems(row, 'Number of Shares', 'Book Value')
        if not ok:
            raise ValueError(f'Missing columns for {row}')
        qty = Decimal(qty)
        book_value, currency = morgan_price(value)
        purchase_price = fixup_price2(self.entry_date, currency, book_value / qty)

        self.deposit(qty, purchase_price, 'RS', self.entry_date)
        self.qty_delta = qty
        return True

    def parse_dividend_reinvest(self, row):
        '''Reinvestment of dividend through bying same share'''
        if self.activity != 'You bought (dividend)':
            return False

        qty, price, ok = getitems(row, 'Number of Shares', 'Share Price')
        if not ok:
            raise ValueError(f'Missing columns for {row}')

        qty = Decimal(qty)
        price, currency = morgan_price(price)

        amount = fixup_price(self.entry_date, currency, f'{price * -qty}')
        self.dividend_reinvest(amount)

        purchase_price = fixup_price2(self.entry_date, currency, price)
        self.deposit(qty, purchase_price, 'Dividend re-invest')
        return True

    def parse_sale(self, row):
        if self.activity != 'Sale':
            return False
        qty, price, ok = getitems(row, 'Number of Shares', 'Share Price')
        if not ok:
            raise ValueError(f'Missing colummns for {row}')
        price, currency = morgan_price(price)
        qty = Decimal(qty)
        price = Decimal(price)

        self.sell(qty, price)
        return True

    def parse_deposit(self, row):
        if self.activity != 'Share Deposit' and self.activity != 'Historical Purchase':
            return False
        qty, ok = getitems(row, 'Number of Shares')
        if not ok:
            raise ValueError(f'Missing columns for {row}')
        qty = Decimal(qty)
        price = currency_converter[(self.symbol, self.entry_date)]
        purchase_price = fixup_price2(self.entry_date, 'ESPPUSD', price)

        self.deposit(qty, purchase_price, 'ESPP', self.entry_date)
        return True

    def parse_dividend_cash(self, row):
        '''This, despite its logged description, results in shares-reinvest'''
        if self.activity != 'Dividend (Cash)':
            return False
        qty, qty_ok = getitems(row, 'Number of Shares')
        cash, cash_ok = getitems(row, 'Cash')

        if qty_ok and cash_ok:
            raise ValueError(f'Unexpected cash+shares for dividend: {row}')

        if qty_ok:
            qty = Decimal(qty)
            price = currency_converter[(self.symbol, self.entry_date)]
            purchase_price = fixup_price2(self.entry_date, 'USD', price)
            self.deposit(qty, purchase_price, 'Dividend re-invest (Cash)', self.entry_date)

            amount = fixup_price(self.entry_date, 'USD', f'{price * -qty}')
            self.dividend_reinvest(amount)

        if cash_ok:
            amount = fixup_price(self.entry_date, 'USD', cash)
            self.dividend(amount)

        return True

    def parse_tax_withholding(self, row):
        '''Record taxes withheld'''
        if self.activity != 'Withholding' and self.activity != 'IRS Nonresident Alien Withholding':
            return False
        taxed, ok = getitems(row, 'Cash')
        if not ok:
            raise ValueError(f'Expected Cash data for tax record: {row}')

        # print(f'parse_tax_withholding: date={self.entry_date} activity={self.activity} taxed={taxed}')
        amount = fixup_price(self.entry_date, 'USD', taxed)

        r = { 'type': EntryTypeEnum.TAX,
              'date': self.entry_date,
              'amount': amount,
              'symbol': self.symbol,
              'description': self.activity,
              'source': self.source }

        self.transactions.append(parse_obj_as(Entry, r))
        return True

    def parse_opening_balance(self, row):
        '''Opening balance for shares is used to add historic shares...'''
        if self.activity != 'Opening Balance':
            return False
        qty, bookvalue, ok = \
            getitems(row, 'Number of Shares', 'Book Value')
        if ok:
            qty = Decimal(qty)
            #bookvalue = Decimal(bookvalue)
            price = currency_converter[(self.symbol, self.entry_date)]
            purchase_price = fixup_price2(self.entry_date, 'USD', price)

            #self.deposit(qty, purchase_price, 'RS', self.entry_date)
            return True
        raise ValueError(f'Unexpected opening balance: {row}')

def find_all_tables(document):
    nodes = document.findall('.//{http://www.w3.org/1999/xhtml}table', None)
    rc = []
    for e, n in zip(nodes, range(0, 10000)):
        rc.append(Table(e, n))
    return rc

def morgan_price(price_str):
    '''Parse price string.'''
    # import IPython
    # IPython.embed()
    if ' ' in price_str:
        value, currency = price_str.split(' ')
    else:
        value, currency = price_str, 'USD'

    return Decimal(value.replace('$', '').replace(',', '')), currency

def fixup_price(datestr, currency, pricestr, change_sign=False):
    '''Fixup price.'''
    # print('fixup_price:::', datestr, currency, pricestr, change_sign)
    price, currency = morgan_price(pricestr)
    if change_sign:
        price = price * -1
    exchange_rate = currency_converter.get_currency(currency, datestr)
    return {'currency': currency, "value": price, 'nok_exchange_rate': exchange_rate, 'nok_value': price * exchange_rate }


def fixup_price2(date, currency, value):
    '''Fixup price.'''
    exchange_rate = currency_converter.get_currency(currency, date)
    return Amount(currency=currency, value=value,
                   nok_exchange_rate=exchange_rate,
                   nok_value=value * exchange_rate)

def create_amount(date, price):
    value, currency = morgan_price(price)
    return fixup_price2(date, currency, value)

def sum_amounts(amounts, negative=False):
    if len(amounts) == 0:
        return None

    sign = -1 if negative else 1

    total = sign * amounts[0].value
    nok_total = sign * amounts[0].nok_value
    currency = amounts[0].currency

    for a in amounts[1:]:
        if a.currency != currency:
            raise ValueError(f'Summing {currency} with {a.currency}')
        total += sign * a.value
        nok_total += sign * a.nok_value

    avg_nok_exchange_rate = nok_total / total

    return Amount(currency=currency, value=total,
                  nok_exchange_rate=avg_nok_exchange_rate,
                  nok_value=nok_total)

def fixup_date(morgandate):
    '''Do this explicitly here to learn about changes in the export format'''
    m = re.fullmatch(r'''(\d+)-([A-Z][a-z][a-z])-(20\d\d)''', morgandate)
    if m:
        day = f'{int(m.group(1)):02d}'
        textmonth = m.group(2)
        year = m.group(3)

        if textmonth == 'Jan':
            return f'{year}-01-{day}'
        elif textmonth == 'Feb':
            return f'{year}-02-{day}'
        elif textmonth == 'Mar':
            return f'{year}-03-{day}'
        elif textmonth == 'Apr':
            return f'{year}-04-{day}'
        elif textmonth == 'May':
            return f'{year}-05-{day}'
        elif textmonth == 'Jun':
            return f'{year}-06-{day}'
        elif textmonth == 'Jul':
            return f'{year}-07-{day}'
        elif textmonth == 'Aug':
            return f'{year}-08-{day}'
        elif textmonth == 'Sep':
            return f'{year}-09-{day}'
        elif textmonth == 'Oct':
            return f'{year}-10-{day}'
        elif textmonth == 'Nov':
            return f'{year}-11-{day}'
        elif textmonth == 'Dec':
            return f'{year}-12-{day}'

    raise ValueError(f'Illegal date: "{morgandate}"')

def getitem(row, colname):
    '''Get a named item from a row, or None if nothing there'''
    if colname not in row:
        return None
    item = row[colname]
    if isinstance(item, float):
        if math.isnan(item):
            return None
        return Decimal(f'{item}')
    if isinstance(item, str) and item == '':
        return None
    return item

def getitems(row, *colnames):
    ok = True
    rc = []
    for cn in colnames:
        i = getitem(row, cn)
        rc.append(i)
        if i is None:
            ok = False
    rc.append(ok)
    return tuple(rc)

def getoptcolitem(row, column, default_value):
    '''If a column exist, return its value, otherwise the default value'''
    if column in row:
        item = row[column]
        if item is not None and item != '':
            return item
    return default_value

def parse_rsu_holdings_table(state, recs):
    state.symbol = 'CSCO'   # Fail on other types of shares
    for row in recs:
        # print(f'RSU-Holdings: {row}')
        fund, date, buy_price, qty, ok = getitems(row, 'Fund', 'Acquisition Date', 'Cost Basis Per Share *', 'Total Shares You Hold')
        if ok:
            if not re.fullmatch(r'''CSCO\s.*''', fund):
                raise ValueError(f'Non-Cisco RSU shares: {fund}')
            date = fixup_date(date)
            qty = Decimal(qty)
            price, currency = morgan_price(buy_price)
            purchase_price = fixup_price2(date, currency, price)
            state.entry_date = date
            state.deposit(qty, purchase_price, 'RS', date)
            # print(f'### RSU {qty} {date} {price}')

def parse_espp_holdings_table(state, recs):
    for row in recs:
        # print(f'ESPP-Holdings: {row}')
        if state.parse_fund_symbol(row, 'Grant Date'):
            continue

        offeringtype = getoptcolitem(row, 'Offering Type', 'Contribution')
        date, qty, ok = getitems(row, 'Purchase Date', 'Total Shares You Hold')
        if ok:
            assert(state.symbol == 'CSCO')
            date = fixup_date(date)
            state.entry_date = date
            qty = Decimal(qty)
            price = currency_converter[(state.symbol, state.entry_date)]
            if offeringtype == 'Contribution':
                # Regular ESPP buy at reduced price
                purchase_price = fixup_price2(date, 'ESPPUSD', price)
                state.deposit(qty, purchase_price, 'ESPP', date)
                # print(f'### ESPP {qty} {date} {price}')
            elif offeringtype == 'Dividend':
                # Reinvested dividend from ESPP shares at regular price
                purchase_price = fixup_price2(date, 'USD', price)
                state.deposit(qty, purchase_price, 'Reinvest', date)
            else:
                raise ValueError(f'Unexpected offering type: {offeringtype}')

def parse_rsu_activity_table(state, recs):
    ignore = {
        'Opening Value': True,
        'Closing Value': True,

        # The following are ignored, but it should be ok:
        # 'Cash Transfer Out' is for dividends moved from "Activity" table
        # to the RSU cash header of that table, and the 'Cash Transfer In'
        # is the counterpart in the RSU cash header.
        # The 'Transfer out' also shows up as a withdrawal, which is handled,
        # so we ignore that here too.
        'Cash Transfer In': True,
        'Cash Transfer Out': True,
        'Transfer out': True,
        'Historical Transaction': True, # TODO: This should update cash-balance
    }

    # Record QTY deltas for RSUs so the RSU holdings table is only used for
    # what is not recorded as proper transactions
    transaction_qtys = []

    for row in recs:
        if state.parse_fund_symbol(row, 'Entry Date'):
            continue
        state.parse_entry_date(row)
        state.parse_activity(row)

        if state.parse_rsu_release(row):
            transaction_qtys.append(state.qty_delta)
            continue

        if state.parse_dividend_reinvest(row):
            continue

        if state.parse_sale(row):
            transaction_qtys.append(state.qty_delta)
            continue

        if state.parse_dividend_cash(row):
            continue

        if state.parse_tax_withholding(row):
            continue

        if state.parse_opening_balance(row):
            continue

        if state.activity in ignore:
            continue

        raise ValueError(f'Unknown RSU activity: "{state.activity}"')

    return transaction_qtys

def parse_espp_activity_table(state, recs):
    ignore = {
        'Opening Value': True,
        'Closing Value': True,
        'Adhoc Adjustment': True,
        'Transfer out': True,
        'Historical Transaction': True,
        'Wash Sale Adjustment': True,
        'Cash Transfer In': True,
        'Cash Transfer Out': True,
    }

    for row in recs:
        if state.parse_fund_symbol(row, 'Entry Date'):
            continue
        state.parse_entry_date(row)
        state.parse_activity(row)

        if state.parse_dividend_reinvest(row):
            continue

        if state.parse_sale(row):
            continue

        if state.parse_deposit(row):
            continue

        if state.parse_dividend_cash(row):
            continue

        if state.parse_tax_withholding(row):
            continue

        if state.activity in ignore:
            continue

        raise ValueError(f'Unknown ESPP activity: "{state.activity}"')

    return state.transactions

class Withdrawal:
    '''Given three tables for withdrawal, extract information we need'''
    def __init__(self, wd, sb, np):
        self.wd = wd
        self.sb = sb
        self.np = np

        self.is_wire = False
        self.has_wire_fee = False

        assert(self.wd.data[3][2] =='Settlement Date:')
        self.entry_date = fixup_date(self.wd.data[3][3])

        assert(self.wd.data[3][0] == 'Fund')
        self.fund = self.wd.data[3][1]
        m = re.fullmatch(r'''([A-Za-z]+)\s+-.*''', self.fund)
        if not m:
            raise ValueError(f'Unexpected symbol format: {self.fund}')
        self.symbol = m.group(1)

        gross = []
        fees = []
        net = []

        for row in self.sb.rows:
            if 'Gross Proceeds' in row[0]:
                gross.append(create_amount(self.entry_date, row[1]))
            if 'Fee' in row[0]:
                fees.append(create_amount(self.entry_date, row[1]))
            if 'Wire Fee' in row[0]:
                has_wire_fee = True

        m = re.fullmatch(r'''Net Proceeds: (.*)''', self.np.data[0][0])
        if m:
            net.append(create_amount(self.entry_date, m.group(1)))

        assert(len(gross) == 1)
        assert(len(net) == 1)

        self.gross_amount = sum_amounts(gross)
        self.fees_amount = sum_amounts(fees)
        self.net_amount = sum_amounts(net, negative=True)

        assert(self.wd.data[5][0] == 'Delivery Method:')
        if 'Transfer funds via wire' in self.wd.data[5][1]:
            self.is_wire = True

        if 'Historical sale of shares' in self.wd.data[5][1] and has_wire_fee:
            self.is_wire = True

def parse_withdrawal_sales(state, sales):
    '''Withdrawals from sale of shares'''
    for wd, sb, np in sales:
        w = Withdrawal(wd, sb, np)
        if w.is_wire:
            assert(w.symbol != 'Cash')   # No Cash-fund for sale withdrawals
            state.wire_transfer(w.entry_date, w.net_amount, w.fees_amount)
        else:
            raise ValueError(f'Sales withdrawal w/o wire-transfer: wd={wd.data} sb={sb.data} np={np.data}')

def parse_withdrawal_proceeds(state, proceeds):
    '''Withdrawal of accumulated Cash (it seems)'''
    for wd, pb, np in proceeds:
        w = Withdrawal(wd, pb, np)
        if w.is_wire:
            assert(w.symbol == 'Cash')   # Proceeds withdrawal is for cash
            state.wire_transfer(w.entry_date, w.net_amount, w.fees_amount)
        else:
            raise ValueError(f'Proceeds withdrawal w/o wire-transfer: wd={wd.data} pb={pb.data} np={np.data}')

def decode_headers(mi):
    '''Force a MultiIndex or Index object into a plain array-of-arrays'''
    rc = []
    if isinstance(mi, MultiIndex):
        for lvl in range(0, mi.nlevels):
            line = []
            for n in range(0, mi.levshape[lvl]):
                line.append(str(mi[n][lvl]))
            rc.append(line)
    elif isinstance(mi, Index):
        rc.append([str(x) for x in mi.values])
    return rc

def istag(elem, tag):
    if not isinstance(elem.tag, str):
        return False
    m = re.fullmatch(r'''\{(.*)\}(.*)''', elem.tag)
    if m:
        standard = m.group(1)
        tagname = m.group(2)
        if tagname == tag:
            return True
    return False

def elem_enter(elem, tag):
    for x in elem:
        if istag(x, tag):
            return x
        return None
    return None

def elem_filter(elem, tag):
    rc = []
    for e in elem:
        if istag(e, tag):
            rc.append(e)
    return rc

def fixuptext(text):
    if text is None:
        return None

    substitute = {
        ord('\t'): ' ',
        ord('\n'): ' ',
        ord('\r'): ' ',
        0xA0: ' ', # Non-breaking space => Regular space
    }
    rc = text.translate(substitute)
    while True:
        m = re.fullmatch(r'''(.*)\s\s+(.*)''', rc)
        if m:
            rc = f'{m.group(1)} {m.group(2)}'
            continue
        break

    m = re.fullmatch(r'''\s*(.*\S)\s*''', rc)
    if m:
        rc = m.group(1)

    if rc == ' ':
        return ''
    return rc

def get_rawtext(elem):
    rc = ''
    if elem.text is not None:
        rc += f' {elem.text}'
    if elem.tail is not None:
        rc += f' {elem.tail}'
    for x in elem:
        rc += f' {get_rawtext(x)}'
    return rc

def get_elem_text(elem):
    return fixuptext(get_rawtext(elem))

def decode_data(table):
    '''Place table-data into a plain array-of-arrays'''
    tb = elem_enter(table, 'tbody')
    if tb is None:
        return None

    rc = []
    for tr in elem_filter(tb, 'tr'):
        row = []
        for te in tr:
            if istag(te, 'th') or istag(te, 'td'):
                row.append(get_elem_text(te))
        rc.append(row)

    return rc

def array_match_2d(candidate, template):
    '''Match a candidate array-of-arrays against a template to match it.

    The template may contain None entries, which will match any candidate
    entry, or it may contain a compiled regular expression - and the result
    will be the candidate data matched by the regex parenthesis. A simple
    string will need to match completely, incl. white-spaces.'''

    if candidate is None or len(candidate) < len(template):
        return None

    rc = []
    for cl, tl in zip(candidate, template):
        if len(cl) != len(tl):
            return None
        line = []
        for n, ci, ti in zip(range(1, 1000), cl, tl):
            if ti is None:
                line.append(str(ci))
                continue
            if isinstance(ti, re.Pattern):
                m = ti.fullmatch(ci)
                if m:
                    line.append(m.group(1))
                    continue
                return None
            if ci == ti:
                line.append(ci)
                continue
            return None
        rc.append(line)

    return rc

def header_match(table, search_header, hline=0):
    '''Use a search-template to look for tables with headers that match.

    The search-template is give to 'array_match_2d' above for matching.
    When a table is matched, the column-names are established from the
    header-line given by 'hline' (default 0).'''
    result = array_match_2d(table.data, search_header)
    if result is None:
        return False
    table.header = result
    table.colnames = result[hline]
    for idx, colname in zip(range(0, 1000), table.colnames):
        table.colname2idx[colname] = idx

    numheaderlines = len(search_header)
    table.rows = table.data[numheaderlines:]

    return True

def find_tables_by_header(tables, search_header, hline=0):
    '''Given a header-template for matching, return all matching tables'''
    rc = []
    for t in tables:
        if header_match(t, search_header, hline):
            rc.append(t)
    return rc

def parse_account_summary_html(tables):
    any = re.compile(r'''(.*)''')
    search_account_summary = [
        [''],
        [any, '', re.compile(r'''Account Summary Statement(.*)''')]
    ]
    summary = find_tables_by_header(tables, search_account_summary, 1)
    assert(len(summary) == 1)
    period = summary[0].data[1][2]
    #print(f'####### period={period} #######')
    m = re.fullmatch(r'''.*Period\s*:\s+(\S+)\s+to\s+(\S+).*''', period)
    if m:
        return (fixup_date(m.group(1)), fixup_date(m.group(2)))
    raise ValueError('Failed to parse Account Summary Statement')

def parse_rsu_holdings_html(all_tables, state):
    '''Look for RSU holdings table and include historic holdings as deposits'''
    search_rsu_holdings = [
        ['Summary of Stock/Shares Holdings'],
        ['Fund', 'Acquisition Date', 'Lot', 'Capital Gain Impact',
         'Gain/Loss', 'Cost Basis *', 'Cost Basis Per Share *',
         'Total Shares You Hold', 'Current Price per Share', 'Current Value' ],
        ['Type of Money: Employee']
    ]

    rsu_holdings = find_tables_by_header(all_tables, search_rsu_holdings, 1)
    if len(rsu_holdings) == 0:
        return

    print(f'### LEN(rsu_holdings)={len(rsu_holdings)}')
    assert(len(rsu_holdings) == 1)

    # print('#### Found RSU holdings')

    parse_rsu_holdings_table(state, rsu_holdings[0].to_dict())

def parse_espp_holdings_html(all_tables, state):
    '''Parse ESPP holdings table and include historic holdings as deposits'''

    search1 = [
        ['Purchase History for Stock/Shares'],
        ['Grant Date', 'Subscription Date', 'Subscription Date FMV',
         'Purchase Date', 'Purchase Date FMV', 'Purchase Price',
         'Qualification Date *', 'Shares Purchased', 'Total Shares You Hold',
         'Current Share Price', 'Current Value']
    ]

    search2 = [
        ['Purchase History for Stock/Shares'],
        ['Grant Date', 'Offering Type', 'Subscription Date',
         'Subscription Date FMV', 'Purchase Date', 'Purchase Date FMV',
         'Purchase Price', 'Qualification Date *', 'Shares Purchased',
         'Total Shares You Hold', 'Current Share Price', 'Current Value']
    ]

    espp_holdings = find_tables_by_header(all_tables, search1, 1)
    if len(espp_holdings) == 0:
        espp_holdings = find_tables_by_header(all_tables, search2, 1)

    if len(espp_holdings) == 0:
        print('No ESPP holdings found for 2021')
        return

    assert(len(espp_holdings) == 1)

    #print('#### Found ESPP holdings')

    parse_espp_holdings_table(state, espp_holdings[0].to_dict())

def parse_rsu_activity_html(all_tables, state):
    '''Look for the RSU table and parse it'''
    search_rsu_header = [
        ['Activity'],
        ['Entry Date', 'Activity', 'Type of Money', 'Cash',
         'Number of Shares', 'Share Price', 'Book Value', 'Market Value']
    ]

    rsu = find_tables_by_header(all_tables, search_rsu_header, 1)
    if len(rsu) == 0:
        return

    assert len(rsu) == 1
    parse_rsu_activity_table(state, rsu[0].to_dict())

def parse_espp_activity_html(all_tables, state):
    '''Look for the ESPP table and parse it'''
    any = re.compile(r'''(.*)''')
    search_espp_header = [
        ['Activity'],
        ['Entry Date', 'Activity', 'Cash',
         'Number of Shares', 'Share Price', 'Market Value', any]
    ]

    espp = find_tables_by_header(all_tables, search_espp_header, 1)

    if len(espp) == 0:
        search_espp_header = [
            ['Activity'],
            ['Entry Date', 'Activity', 'Cash',
             'Number of Shares', 'Share Price', 'Market Value']
        ]

        espp = find_tables_by_header(all_tables, search_espp_header, 1)

    print(f'### ESPP tables found: {len(espp)}')

    if len(espp) == 1:
        parse_espp_activity_table(state, espp[0].to_dict())
    elif len(espp) != 0:
        raise ValueError(f'Expected 0 or 1 ESPP tables, got {len(espp)}')

def parse_withdrawals_html(all_tables, state):
    search_withdrawal_header = [
        [re.compile(r'''Withdrawal on (.*)''')]
    ]
    search_salebreakdown = [
        [re.compile(r'''\s*(Sale Breakdown)''')]
    ]
    search_proceedsbreakdown = [
        [re.compile(r'''\s*(Proceeds Breakdown)''')]
    ]
    search_net_proceeds = [
        [None]
    ]

    withdrawals = find_tables_by_header(all_tables, search_withdrawal_header)

    sales = []
    proceeds = []
    netproceeds = []
    for wd in withdrawals:
        nexttab = [all_tables[wd.idx + 1]]
        nextnexttab = [all_tables[wd.idx + 2]]

        np = find_tables_by_header(nextnexttab, search_net_proceeds)
        if len(np) != 1:
            raise ValueError(f'Unable to parse net-proceeds: {nextnexttab}')

        sb = find_tables_by_header(nexttab, search_salebreakdown)
        if len(sb) == 1:
            sales.append((wd, sb[0], np[0]))
            continue

        pb = find_tables_by_header(nexttab, search_proceedsbreakdown)
        if len(pb) == 1:
            proceeds.append((wd, pb[0], np[0]))
            continue

        raise ValueError('Unable to parse "Sale/Proceeds Breakdown"')

    parse_withdrawal_sales(state, sales)
    parse_withdrawal_proceeds(state, proceeds)

def parse_cash_holdings_html(all_tables, state):
    search_cash_holding_header = [
        ['Summary of Cash Holdings'],
        ['Fund', 'Current Value'],
    ]
    cashtabs = find_tables_by_header(all_tables, search_cash_holding_header)
    total = Decimal('0.00')
    for ct in cashtabs:
        for row in ct.rows:
            if len(row) == 2 and row[0] == 'Cash - USD':
                value, currency = morgan_price(row[1])
                assert(currency == 'USD')
                total += Decimal(value)
                print(f'### Cash: {value}')
    print(f'### Cash holdings: {total}')
    cash = fixup_price2('2021-12-31', 'USD', total)
    state.cashadjust('2021-12-31', cash, 'Closing balance 2021')

def morgan_html_import(html_fd, filename):
    '''Parse Morgan Stanley HTML table file.'''

    document = html5lib.parse(html_fd)
    all_tables = find_all_tables(document)

    state = ParseState(filename)

    start_period, end_period = parse_account_summary_html(all_tables)

    if end_period == '2021-12-31':
        # Parse the holdings tables to produce deposits to establish the
        # holdings at the end of 2021.
        print('Parse RSU holdings ...')
        parse_rsu_holdings_html(all_tables, state)
        print('Parse ESPP holdings ...')
        parse_espp_holdings_html(all_tables, state)
        print('Parse Cash holdings ...')
        parse_cash_holdings_html(all_tables, state)

    elif start_period == '2022-01-01' and end_period == '2022-12-31':
        print('Parse RSU activity ...')
        parse_rsu_activity_html(all_tables, state)
        print('Parse ESPP activity ...')
        parse_espp_activity_html(all_tables, state)
        print('Parse withdrawals ...')
        parse_withdrawals_html(all_tables, state)
        state.flush_dividend()
    else:
        raise ValueError(f'Period {start_period} - {end_period} is unexpected')

    print('Done')

    transes = sorted(state.transactions, key=lambda d: d.date)

    return Transactions(transactions=transes)

def read(html_file, filename='') -> Transactions:
    '''Main entry point of plugin. Return normalized Python data structure.'''
    return morgan_html_import(html_file, filename)
