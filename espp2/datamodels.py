'''Data models for espp2'''
# pylint: disable=too-few-public-methods, missing-class-docstring, no-name-in-module
# pylint: disable=no-self-argument

from datetime import date
from typing import List, Literal, Annotated, Union, Optional, Any, Dict
from enum import Enum
from decimal import Decimal
from pydantic import (field_validator, model_validator, ConfigDict,
                      BaseModel, validator, Field, RootModel)
from espp2.fmv import FMV

from IPython import embed
#
# Transactions data model
#
#########################################################################

# Singleton caching stock and currency data
fmv = FMV()

class EntryTypeEnum(str, Enum):
    '''Entry type'''
    BUY = 'BUY'
    DEPOSIT = 'DEPOSIT'
    TAX = 'TAX'
    TAXSUB = 'TAXSUB'
    DIVIDEND = 'DIVIDEND'
    DIVIDEND_REINV = 'DIVIDEND_REINV'
    WIRE = 'WIRE'
    SELL = 'SELL'
    TRANSFER = 'TRANSFER'
    FEE = 'FEE'
    CASHADJUST = 'CASHADJUST'

    def __str__(self):
        return self.value

class Amount(BaseModel):
    '''Amount'''
    currency: str
    nok_exchange_rate: Decimal
    nok_value: Decimal
    value: Decimal

    def __init__(self, amountdate=None, **data):
        '''Initialize amount from currency, date and value'''
        if amountdate and 'nok_exchange_rate' not in data:
            exchange_rate = fmv.get_currency(data['currency'], amountdate)
            data['nok_exchange_rate'] = exchange_rate
            data['nok_value'] = Decimal(str(data['value'])) * exchange_rate
        elif not data:
            data['nok_exchange_rate'] = 0
            data['nok_value'] = 0
            data['currency'] = 'NA'
            data['value'] = 0
        super().__init__(**data)

    def __str__(self):
        if self.currency == 'USD':
            return f'${self.value}'
        return f'{self.currency}{self.value}'
    def __format__(self, format_spec):
        return f'${self.value:{format_spec}}'

    def __mul__(self, qty: Decimal):
        result = self.model_copy()
        result.value = result.value * qty
        result.nok_value = result.nok_value * qty
        return result

    def __add__(self, other):
        result = self.model_copy()
        result.value = result.value + other.value
        result.nok_value = result.nok_value + other.nok_value
        return result
    def __radd__(self, other):
        if isinstance(other, int) and other == 0:
            return self
        result = self.model_copy()
        result.value = result.value + other.value
        result.nok_value = result.nok_value + other.nok_value
        return result

class PositiveAmount(Amount):
    '''Positive amount'''
    @field_validator('value', 'nok_value')
    @classmethod
    def value_validator(cls, v):
        '''Validate value'''
        if v < 0:
            raise ValueError('Negative value', v)
        return v
class NegativeAmount(Amount):
    '''Negative amount'''
    @field_validator('value', 'nok_value')
    @classmethod
    def value_validator(cls, v):
        '''Validate value'''
        if v > 0:
            raise ValueError('Must be negative value', v)
        return v

duplicates = {}
def get_id(values: Dict[str, Any]):
    '''Get id'''
    embed()
    d = values['source'] + str(values['date'])
    if d in duplicates:
        duplicates[d] += 1
    else:
        duplicates[d] = 1

    id = f"{values['type']} {str(values['date'])}"
    if 'qty' in values:
        id += ' ' + str(values['qty'])
    return id + ':' + str(duplicates[d])

class TransactionEntry(BaseModel):
    pass
    # TODO[pydantic]: We couldn't refactor the `validator`, please replace it by `field_validator` manually.
    # Check https://docs.pydantic.dev/dev-v2/migration/#changes-to-validators for more information.
    # @validator('id', pre=True, always=True, check_fields=False)
    # def validate_id(cls, v, values):
    #     '''Validate id'''
    #     return get_id(values)

    # @field_validator('id', mode='after')
    # @classmethod
    # def validate_id(cls, v, values):
    #     '''Validate id'''
    #     return get_id(values)

class Buy(TransactionEntry):
    '''Buy transaction'''
    type: Literal[EntryTypeEnum.BUY]
    date: date
    symbol: str
    qty: Decimal
    purchase_price: Amount
    source: str
    id: str = Optional[str]

    @field_validator('purchase_price')
    @classmethod
    def purchase_price_validator(cls, v, values):
        '''Validate purchase price'''
        if v.nok_value < 0 or v.value < 0:
            raise ValueError('Negative values for purchase price', v, values)
        return v
    model_config = ConfigDict(extra="allow")

class Deposit(TransactionEntry):
    '''Deposit transaction'''
    type: Literal[EntryTypeEnum.DEPOSIT]
    date: date
    qty: Decimal
    symbol: str
    description: str
    purchase_price: Amount
    purchase_date: Optional[date] = None
    source: str
    id: str = Optional[str]

    @field_validator('purchase_price')
    @classmethod
    def purchase_price_validator(cls, v, values):
        '''Validate purchase price'''
        if v.nok_value < 0 or v.value < 0:
            raise ValueError('Negative values for purchase price', values)
        return v
    model_config = ConfigDict(extra="allow")

class Tax(TransactionEntry):
    '''Tax withheld transaction'''
    type: Literal[EntryTypeEnum.TAX]
    date: date
    symbol: str
    description: str
    amount: NegativeAmount
    source: str
    id: str = Optional[str]

class Taxsub(TransactionEntry):
    '''Tax returned transaction'''
    type: Literal[EntryTypeEnum.TAXSUB]
    date: date
    symbol: str
    description: str
    amount: Amount
    source: str
    id: str = Optional[str]

class Dividend(TransactionEntry):
    '''Dividend transaction'''
    type: Literal[EntryTypeEnum.DIVIDEND]
    date: date
    symbol: str
    amount: Optional[PositiveAmount] = None
    amount_ps: Optional[PositiveAmount] = None
    source: str
    id: str = Optional[str]

    @model_validator(mode="before")
    @classmethod
    def check_dividend_data(cls, values):
        '''Lookup dividend data from the external API and put those records in the data model'''
        values['exdate'], values['declarationdate'], values['dividend_dps'] = fmv.get_dividend(
            values['symbol'], values['date'])
        return values
    model_config = ConfigDict(extra="allow")


class Dividend_Reinv(TransactionEntry):
    '''Dividend reinvestment transaction'''
    type: Literal[EntryTypeEnum.DIVIDEND_REINV]
    date: date
    symbol: str
    amount: Amount
    description: str
    source: str
    id: str = Optional[str]

class Wire(TransactionEntry):
    '''Wire transaction'''
    type: Literal[EntryTypeEnum.WIRE] = Field(const=True)
    date: date
    amount: Amount
    description: str
    fee: Optional[NegativeAmount] = None
    source: str
    id: str = Optional[str]

class Sell(TransactionEntry):
    '''Sell transaction'''
    type: Literal[EntryTypeEnum.SELL]
    date: date
    symbol: str
    qty: Annotated[Decimal, Field(lt=0)]
    fee: Optional[NegativeAmount] = None
    amount: Amount
    description: str
    source: str
    id: str = Optional[str]

class Fee(TransactionEntry):
    '''Independent Fee'''
    type: Literal[EntryTypeEnum.FEE]
    date: date
    amount: NegativeAmount
    source: str
    id: str = Optional[str]

class Transfer(TransactionEntry):
    '''Transfer transaction'''
    type: Literal[EntryTypeEnum.TRANSFER]
    date: date
    symbol: str
    qty: Decimal
    # amount: Amount
    fee: Optional[NegativeAmount] = 0
    source: str
    id: str = Optional[str]

class Cashadjust(TransactionEntry):
    '''Adjust the cash-balance with a positive or negative adjustment'''
    type: Literal[EntryTypeEnum.CASHADJUST]
    date: date
    amount: Amount
    description: str


Entry = Annotated[Union[Buy, Deposit, Tax, Taxsub, Dividend,
                        Dividend_Reinv, Wire, Sell, Transfer, Fee, Cashadjust],
                        Field(discriminator="type")]

class Transactions(BaseModel):
    '''Transactions'''
    transactions: list[Entry]


#########################################################################

# Wires data model
class WireAmount(BaseModel):
    date: date
    currency: str
    nok_value: Decimal
    value: Decimal
# class Wire(BaseModel):
#     date: date
#     wire: WireAmount
class Wires(RootModel):
    root: list[WireAmount]

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]

# Holdings data model
class Stock(BaseModel):
    '''Stock positions'''
    symbol: str
    date: date
    qty: Decimal
    tax_deduction: Decimal
    purchase_price: Amount

    # @validator('purchase_price', pre=True, always=True)
    # TODO[pydantic]: We couldn't refactor the `validator`, please replace it by `field_validator` manually.
    # Check https://docs.pydantic.dev/dev-v2/migration/#changes-to-validators for more information.
    @validator('purchase_price', pre=True, always=True)
    def set_purchase_price(cls, value, values):
        '''Set purchase price and calculate nok value if needed'''
        if isinstance(value, Amount):
            return value
        if 'nok_exchange_rate' not in value:
            return Amount(amountdate=values['date'], currency=value['currency'],
                          value=value['value'])
        return value
    model_config = ConfigDict(extra="allow")

class CashEntry(BaseModel):
    '''Cash entry'''
    date: date
    description: str
    amount: Amount
    transfer: Optional[bool] = False

class Holdings(BaseModel):
    '''Stock holdings'''
    year: int
    broker: str
    stocks: list[Stock]
    cash: list[CashEntry]

class EOYBalanceItem(BaseModel):
    '''EOY balance item'''
    symbol: str
    qty: Decimal
    amount: Amount
    fmv: Decimal
    model_config = ConfigDict(extra="allow")

class EOYDividend(BaseModel):
    '''EOY dividend'''
    symbol: str
    amount: Amount
    gross_amount: Amount
    post_tax_inc_amount: Optional[Amount] = None
    tax: Amount # Negative
    tax_deduction_used: Decimal # NOK

class SalesPosition(BaseModel):
    '''Sales positions'''
    symbol: str
    qty: Decimal
    sale_price: Amount
    purchase_price: Amount
    purchase_date: date
    gain_ps: Amount
    tax_deduction_used: Decimal
class EOYSales(BaseModel):
    '''EOY sales'''
    symbol: str
    date: date
    qty: Decimal
    amount: Amount
    fee: Optional[Amount] = None
    from_positions: list[SalesPosition]
    totals: Optional[dict] = None
    # total_gain: Amount

class TaxReport(BaseModel):
    '''Tax report'''
    eoy_balance: Dict[int, list[EOYBalanceItem]]
    ledger: dict
    dividends: list[EOYDividend]
    buys: list
    sales: Dict[str, list[EOYSales]]
    # cash: dict
    cash_ledger: list
    unmatched_wires: list[WireAmount]
    prev_holdings: Optional[Holdings] = None

class CashModel(BaseModel):
    '''Cash model'''
    cash: List[CashEntry] = []

class ForeignShares(BaseModel):
    '''Foreign shares'''
    symbol: str
    isin: str
    country: str
    account: str
    shares: Decimal
    wealth: Annotated[Decimal, Field(ge=0)]
    # Share of taxable dividend after October 6.
    post_tax_inc_dividend: Optional[Annotated[Decimal, Field(ge=0, decimal_places=0)]] = None
    # Taxable dividend
    dividend: Annotated[Decimal, Field(ge=0, decimal_places=0)]
    taxable_gain: Annotated[Decimal, Field(decimal_places=0)]
    taxable_post_tax_inc_gain: Optional[Annotated[Decimal, Field(decimal_places=0)]] = None
    tax_deduction_used: Annotated[Decimal, Field(ge=0, decimal_places=0)]

class CreditDeduction(BaseModel):
    '''Credit deduction'''
    symbol: str
    country: str
    income_tax: Annotated[Decimal, Field(ge=0, decimal_places=0)]
    gross_share_dividend: Annotated[Decimal, Field(ge=0, decimal_places=0)]
    tax_on_gross_share_dividend: Annotated[Decimal, Field(ge=0, decimal_places=0)]

class TransferRecord(BaseModel):
    '''Transfers'''
    date: date
    amount_sent: Annotated[Decimal, Field(ge=0, decimal_places=0)]
    amount_received: Annotated[Decimal, Field(gt=0, decimal_places=0)]
    gain: Annotated[Decimal, Field(decimal_places=0)]
    description: str
class CashSummary(BaseModel):
    '''Cash account'''
    transfers: list[TransferRecord]
    remaining_cash: Amount
    holdings: list[CashEntry]
    gain: Decimal

class TaxSummary(BaseModel):
    '''Tax summary'''
    year: int
    foreignshares: list[ForeignShares]
    credit_deduction: list[CreditDeduction]
    cashsummary: CashSummary


class ESPPResponse(BaseModel):
    '''ESPP response'''
    holdings: Holdings
    tax_report: TaxReport
    summary: TaxSummary

class Fundamentals(BaseModel):
    '''Fundamentals'''
    name: str
    isin: str
    country: str
    symbol: str

class ExpectedBalance(BaseModel):
    '''Expected balance. Note only supports a single symbol'''
    symbol: str
    qty: Decimal
