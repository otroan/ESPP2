def df_active_balance(df: pd.DataFrame) -> pd.DataFrame:
    '''
    Given a set of trades using FIFO sell order calculate the final set of stock sets.
    Input: dataframe of trades with columns: Symbol, Open date, Qty, Type (BUY/SELL)
    Returns: dataframe with the ending balance
    '''
    def fifo(dfg):
        try:
            no_sells = abs(dfg[dfg['PN'] == 'N']['CS'].iloc[-1])
        except IndexError:
            no_sells = 0
        try:
            no_buys = abs(dfg[dfg['PN'] == 'P']['CS'].iloc[-1])
        except IndexError:
            no_buys = 0
        if no_sells > no_buys:
            raise Exception(f'Selling stocks you do not have. {dfg}')
        if dfg[dfg['CS'] < 0]['qty'].count():
            subT = dfg[dfg['CS'] < 0]['CS'].iloc[-1]
            dfg['qty'] = np.where((dfg['CS'] + subT) <= 0, 0, dfg['qty'])
            dfg = dfg[dfg['qty'] > 0]
            if (len(dfg) > 0):
                dfg['qty'].iloc[0] = dfg['CS'].iloc[0] + subT
        return dfg

    df['PN'] = np.where(df['qty'] > 0, 'P', 'N')
    df['CS'] = df.groupby(['symbol', 'PN'])['qty'].cumsum()
    return df.groupby(['symbol'], as_index=False, group_keys=False)\
        .apply(fifo) \
        .drop(['CS', 'PN'], axis=1)




class Balance():
    def __init__(self, balance, date = None) -> None:
        self.balance = balance
        self.date = date

    def total_shares(self):
        return self.balance['qty'].sum()

    def total_shares_by_symbol(self):
        return self.balance.groupby(['symbol'])['qty'].sum().to_dict()

    def holdings(self):
        return  self.balance.to_dict('records')

    def eoy(self):
        f = FMV()
        eoy_exchange_rate = f.get_currency('USD', self.date)
        b = self.balance.groupby(['symbol'])['qty'].sum().to_dict()
        for k,v in b.items():
            fmv = eoy_share_fmv = f[k, self.date]
            b[k] = {'qty': v, 'total_nok': eoy_exchange_rate * v * fmv, 'nok_exchange_rate': eoy_exchange_rate, 'fmv': fmv}
        return b

class Transactions():
    def generate_holdings(self, year, holdings, transactions):
        ''' Generate holdings for this year, only used in case of missing holdings file '''
        if holdings:
            for h in holdings['stocks']:
                h['date'] = pd.to_datetime(h['date'])

            holdings_year = holdings['year']
            transactions = [t for t in transactions if t['date'].year <= year and t['date'].year > holdings_year]
            df = pd.DataFrame(holdings['stocks'] + transactions)
        else:
            transactions = [t for t in transactions if t['date'].year <= year]
            df = pd.DataFrame(transactions)

        balance = df_active_balance(df)
        b = Balance(balance)
        holdings = {'year': year}
        holdings['stocks'] = b.holdings()
        logger.debug(f'We think you had: {b.total_shares()} in {year}')
        logger.debug(f'We think you had: {b.total_shares_by_symbol()} in {year}')
        holdings['cash'] = {}
        return holdings

    def __init__(self, year, holdings, transactions) -> None:
        '''
        Goal: Get us to a known state where we have transactions for the tax year, and the holdings for last year
        Use cases:
        1. New hire. No holdings file. All transactions from last year
        2. Previous year holding file. Transactions for this year.
        3. No holdings file. All transactions for all years
        4. Manual "made-up" holdings file. All transactiosn for that year (Bjorn)
        5. Previous years ESPP tool pickle holdings.
        For 3-4, must generate holdings for all years up to previous year.
        5 equals 2.
        '''

        first_year = year
        for t in transactions:
            t['date'] = pd.to_datetime(t['date'])
            if t['date'].year < first_year:
                first_year = t['date'].year
            # if t['type'] == 'DEPOSIT' or t['type'] == 'SELL':
            #     print(f'{t["type"]} {t["symbol"]} {t["qty"]}')

        # Figure out if we need to calculate previous year holdings:
        is_holdings_missing = False
        if holdings and holdings['year'] != year - 1:
            is_holdings_missing = True
        if not holdings and first_year < year:
            is_holdings_missing = True
        if is_holdings_missing:
            logger.debug(f'Generate holdings file for {year}')
            holdings = self.generate_holdings(year - 1, holdings, transactions)
            # Write out generated holdings file
            # Check if there are any current transactions against made-up initial holdings file.
            print("HOLDINGS!!!", holdings)
        if holdings:
            if holdings['year'] != year - 1:
                raise Exception('Holdings file must be from previous year!', holdings['year'], year)
            for h in holdings['stocks']:
                h['date'] = pd.to_datetime(h['date'])

            self.stock_holdings = holdings['stocks']
            self.cash_holdings = holdings['cash']

        else:
            self.stock_holdings = []
            self.cash_holdings = None

        # Filter transactions file to current year
        transactions = [t for t in transactions if t['date'].year == year]

        self.transactions = transactions
        self.trades = [t for t in transactions if t['type'] == 'BUY' or t['type'] == 'DEPOSIT' or t['type'] == 'SELL']
        self.year = year

    def buys(self):
        '''TODO: Deal with CASH account'''
        c = Cash()
        buys = []
        for t in self.trades:
            # if t['type'] == 'BUY':
            #     c.credit(t['date'], t['amount'])
            # elif t['type'] == 'DEPOSIT' and t['description'] == 'Div Reinv':
            #     print('TTTT:', t)
            #     c.credit(t['date'], t['purchase_price']['amount'])
            if t['type'] == 'BUY' or t['type'] == 'DEPOSIT':
                buys.append(t)
        return buys


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
    transactions = json.load(args.transaction_file)
    if args.holdings_file:
        prev_holdings = json.load(args.holdings_file)
    else:
        prev_holdings = None

    # t = Transactions(int(args.year), prev_holdings, transactions)

    # TODO: Pre-calculate holdings if required
    p = Positions(prev_holdings, transactions)

    # End of Year Balance (formueskatt)
    print('End of year balance:', p.eoy_balance(args.year))

    # Dividends
    print('Dividends: ', p.dividends())

    # Sales
    print('Sales:', p.sales())

    # Buys (just for logging)
    print('Buys:', p.buys())

    # Tax report
    p.tax(args.year)

    # Cash
    # XXXX

    # New holdings
    # XXXX

if __name__ == '__main__':
    main()
