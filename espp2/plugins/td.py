class TDTransactionsCSV(Transactions):
    @staticmethod
    def description_to_type(value):
        if value.startswith('Bought') or value.startswith('TRANSFER OF SECURITY'):
            return 'BUY'
        if value.startswith('Sold'):
            return 'SELL'
        if value.startswith('ORDINARY DIVIDEND'):
            return 'DIVIDEND'
        if value.startswith('W-8 WITHHOLDING'):
            return 'TAX'
        if value.startswith('CLIENT REQUESTED ELECTRONIC FUNDING DISBURSEMENT'):
            return 'WIRE'
        if value.startswith('FREE BALANCE INTEREST'):
            return 'INTEREST'
        if value.startswith('REBATE'):
            return 'REBATE'
        if value.startswith('WIRE INCOMING'):
            return 'DEPOSIT'
        if value.startswith('OFF-CYCLE INTEREST'):
            return 'INTEREST'
        raise Exception(f'Unknown transaction entry {value}')
        return value

    def __init__(self, csv_file, prev_holdings, year) -> None:
        logging.info(f'Reading transactions from {csv_file}')
        df = pd.read_csv(csv_file, converters={'DESCRIPTION': self.description_to_type})
        self.df_trades = None
        self.df_dividend = None
        self.df_tax = None
        self.year = year

        df = df.rename(columns={'DATE': 'date',
                                'TRANSACTION ID': 'transaction_id',
                                'DESCRIPTION': 'type',
                                'SYMBOL': 'symbol',
                                'QUANTITY': 'qty',
                                'PRICE': 'price',
                                'FUND REDEMPTION FEE': 'fee1',
                                'SHORT-TERM RDM FEE': 'rdm',
                                ' DEFERRED SALES CHARGE': 'fee2',
                                'COMMISSION': 'fee3',
                                'AMOUNT': 'amount',
                                })
        print('READ:', df)
        
        ### TODO: Merge Fee columns. Drop other columns
        df['fees'] = df[['fee1', 'fee2', 'fee3']].sum(axis=1)
        
        df['date'] = pd.to_datetime(df['date'], utc=True)
        l = len(df)
        df = df[df['date'].dt.year == self.year]
        if l != len(df):
            logging.warning(f'Filtered out transaction entries from another year. {l} {len(df)}')
            
        df['qty'] = np.where(df['type'] == 'SELL', -1 * df['qty'], df['qty'])
        df['tax_deduction'] = 0

        # Get holdings from previous year
        self.dfprevh = None
        if prev_holdings and os.path.isfile(prev_holdings):
            logging.info(f'Reading previous holdings from {prev_holdings}')
            with open (prev_holdings) as f:
                data = json.load(f)
            #dfprevh = pd.from_dict(data['shares'])
            dfprevh = pd.DataFrame(data['stocks'])
            dfprevh['type'] = 'BUY'
            dfprevh['date'] = pd.to_datetime(dfprevh['date'], utc=True)
            self.dfprevh = dfprevh
            df = pd.concat([dfprevh, df], ignore_index=True)

            dfprevh_cash = pd.DataFrame(data['cash'])

            if not dfprevh_cash.empty:
                dfprevh_cash['date'] = pd.to_datetime(dfprevh_cash['date'], utc=True)
            self.dfprevh_cash = dfprevh_cash
        else:
            logging.error('No previous year holdings, is this really the first year?')

        df = df.sort_values(by='date')
        df['idx'] = pd.Index(range(len(df.index)))
        self.df = df
        
        self.df_trades = self.df[self.df.type.isin(['BUY', 'SELL'])]
        self.df_dividend = self.df[self.df.type == 'DIVIDEND']
        self.df_tax = self.df[self.df.type == 'TAX']
        self.df_cash = self.df[self.df.type == 'WIRE']
        self.df_fees = self.df[self.df.type == 'FEE'] ### TODO: FIX FIX

