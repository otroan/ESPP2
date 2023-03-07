from pydantic import BaseModel, ValidationError, validator, Field, Extra
from datetime import date
from typing import List, Literal, Annotated, Union, Optional, Any, Dict
from enum import Enum
from decimal import Decimal

#
# Transactions data model
#
#########################################################################

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

    def __str__(self):
        return self.value

class Amount(BaseModel):
    '''Amount'''
    currency: str
    nok_exchange_rate: Decimal
    nok_value: Decimal
    value: Decimal

    def __str__(self):
        if self.currency == 'USD':
            return f'${self.value}'
        return f'{self.currency}{self.value}'
    
    def __mul__(self, qty: Decimal):
        result = self.copy()
        result.value = result.value * qty
        result.nok_value = result.nok_value * qty
        return result

    def __add__(self, other):
        result = self.copy()
        result.value = result.value + other.value
        result.nok_value = result.nok_value + other.nok_value
        return result
    def __radd__(self, other):
        if isinstance(other, int) and other == 0:
            return self
        result = self.copy()
        result.value = result.value + other.value
        result.nok_value = result.nok_value + other.nok_value
        return result

class TransactionEntry(BaseModel):
    @validator('id', pre=True, always=True, check_fields=False)
    def validate_id(cls, v, values):
        '''Validate id'''
        v = ''.join([str(t) for t in values.values()])
        return v
    
class Buy(TransactionEntry):
    '''Buy transaction'''
    type: Literal[EntryTypeEnum.BUY]
    date: date
    symbol: str
    qty: Decimal
    purchase_price: Amount
    id: str = Optional[str]

    @validator('purchase_price')
    def purchase_price_validator(cls, v, values):
        '''Validate purchase price'''
        if v.nok_value < 0 or v.value < 0:
            raise ValueError('Negative values for purchase price', v, values)
        return v

    class Config:
        extra = Extra.allow

class Deposit(TransactionEntry):
    '''Deposit transaction'''
    type: Literal[EntryTypeEnum.DEPOSIT]
    date: date
    qty: Decimal
    symbol: str
    description: str
    purchase_price: Amount
    purchase_date: Optional[date]
    id: str = Optional[str]

    @validator('purchase_price')
    def purchase_price_validator(cls, v, values):
        '''Validate purchase price'''
        if v.nok_value < 0 or v.value < 0:
            raise ValueError('Negative values for purchase price', values)
        return v
    class Config:
        extra = Extra.allow

class Tax(TransactionEntry):
    '''Tax withheld transaction'''
    type: Literal[EntryTypeEnum.TAX]
    date: date
    symbol: str
    description: str
    amount: Amount
    id: str = Optional[str]

class Taxsub(TransactionEntry):
    '''Tax returned transaction'''
    type: Literal[EntryTypeEnum.TAXSUB]
    date: date
    symbol: str
    description: str
    amount: Amount
    id: str = Optional[str]

class Dividend(TransactionEntry):
    '''Dividend transaction'''
    type: Literal[EntryTypeEnum.DIVIDEND]
    date: date
    symbol: str
    amount: Amount
    id: str = Optional[str]

class Dividend_Reinv(TransactionEntry):
    '''Dividend reinvestment transaction'''
    type: Literal[EntryTypeEnum.DIVIDEND_REINV]
    date: date
    symbol: str
    amount: Amount
    description: str
    id: str = Optional[str]

class Wire(TransactionEntry):
    '''Wire transaction'''
    type: Literal[EntryTypeEnum.WIRE]
    date: date
    amount: Amount
    description: str
    fee: Optional[Amount]
    id: str = Optional[str]

class Sell(TransactionEntry):
    '''Sell transaction'''
    type: Literal[EntryTypeEnum.SELL]
    date: date
    symbol: str
    qty: Decimal
    fee: Optional[Amount]
    amount: Amount
    description: str
    id: str = Optional[str]

Entry = Annotated[Union[Buy, Deposit, Tax, Taxsub, Dividend,
                        Dividend_Reinv, Wire, Sell], Field(discriminator="type")]

class Transactions(BaseModel):
    '''Transactions'''
    transactions: list[Entry]




#########################################################################

# Wires data model
class WireAmount(BaseModel):
    currency: str
    nok_value: Decimal
    value: Decimal
class Wire(BaseModel):
    date: date
    wire: WireAmount
class Wires(BaseModel):
    wires: list[Wire]


# Holdings data model
class Stock(BaseModel):
    '''Stock positions'''
    symbol: str
    date: date
    qty: Decimal
    tax_deduction: Decimal
    purchase_price: Amount
    class Config:
        extra = Extra.allow

class Holdings(BaseModel):
    '''Stock holdings'''
    year: int
    broker: str
    stocks: list[Stock]
    cash: list[Wire]

class EOYBalanceItem(BaseModel):
    '''EOY balance item'''
    symbol: str
    qty: Decimal
    amount: Amount
    fmv: Decimal
    class Config:
        extra = Extra.allow

class EOYDividend(BaseModel):
    '''EOY dividend'''
    symbol: str
    amount: Amount
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
    fee: Optional[Amount]
    from_positions: list[SalesPosition]
    totals: Optional[dict]
    # total_gain: Amount

class TaxReport(BaseModel):
    '''Tax report'''
    eoy_balance: Dict[str, list[EOYBalanceItem]]
    ledger: dict
    dividends: list[EOYDividend]
    buys: list
    sales: Dict[str, list[EOYSales]]
    cash: dict
    cash_ledger: list
    unmatched_wires: list
    prev_holdings: Holdings

class CashEntry(BaseModel):
    date: date
    amount: Amount
    transfer: Optional[bool] = False
class CashModel(BaseModel):
    cash: List[CashEntry] = []

class ESPPResponse(BaseModel):
    holdings: Holdings
    tax_report: TaxReport
