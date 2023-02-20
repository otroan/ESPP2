from pydantic import BaseModel, ValidationError, validator, Field, Extra
from datetime import date
from typing import List, Literal, Annotated, Union, Optional, Any
from enum import Enum
from decimal import Decimal

'''
Transactions data model
'''
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

class Amount(BaseModel):
    '''Amount'''
    currency: str
    nok_exchange_rate: Decimal
    nok_value: Decimal
    value: Decimal

class Buy(BaseModel):
    '''Buy transaction'''
    type: Literal[EntryTypeEnum.BUY]
    date: date
    symbol: str
    qty: Decimal
    purchase_price: Amount

    @validator('purchase_price')
    def purchase_price_validator(cls, v, values):
        '''Validate purchase price'''
        if v.nok_value < 0 or v.value < 0:
            raise ValueError('Negative values for purchase price', v, values)
        return v

    class Config:
        extra = Extra.allow

class Deposit(BaseModel):
    '''Deposit transaction'''
    type: Literal[EntryTypeEnum.DEPOSIT]
    date: date
    qty: Decimal
    symbol: str
    description: str
    purchase_price: Amount
    purchase_date: date = None

    @validator('purchase_price')
    def purchase_price_validator(cls, v, values):
        '''Validate purchase price'''
        if v.nok_value < 0 or v.value < 0:
            raise ValueError('Negative values for purchase price', values)
        return v
    class Config:
        extra = Extra.allow

class Tax(BaseModel):
    '''Tax withheld transaction'''
    type: Literal[EntryTypeEnum.TAX]
    date: date
    symbol: str
    description: str
    amount: Amount

class Taxsub(BaseModel):
    '''Tax returned transaction'''
    type: Literal[EntryTypeEnum.TAXSUB]
    date: date
    symbol: str
    description: str
    amount: Amount

class Dividend(BaseModel):
    '''Dividend transaction'''
    type: Literal[EntryTypeEnum.DIVIDEND]
    date: date
    symbol: str
    amount: Amount

class Dividend_Reinv(BaseModel):
    '''Dividend reinvestment transaction'''
    type: Literal[EntryTypeEnum.DIVIDEND_REINV]
    date: date
    symbol: str
    amount: Amount
    description: str
class Wire(BaseModel):
    '''Wire transaction'''
    type: Literal[EntryTypeEnum.WIRE]
    date: date
    amount: Amount
    description: str
    fee: Optional[Amount]
class Sell(BaseModel):
    '''Sell transaction'''
    type: Literal[EntryTypeEnum.SELL]
    date: date
    symbol: str
    qty: Decimal
    fee: Optional[Amount]
    amount: Amount
    description: str


# Deposits = Annotated[Union[ESPP, RS], Field(discriminator="description")] | Deposit
Entry = Annotated[Union[Buy, Deposit, Tax, Taxsub, Dividend,
                        Dividend_Reinv, Wire, Sell], Field(discriminator="type")]


class Transactions(BaseModel):
    transactions: list[Entry]



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

class TaxReport(BaseModel):
    eoy_balance: dict
    dividends: dict
    buys: list
    sales: dict
    cash: dict
    unmatched_wires: list

class CashEntry(BaseModel):
    date: date
    amount: Amount
    transfer: Optional[bool] = False
class CashModel(BaseModel):
    cash: List[CashEntry] = []

class ESPPResponse(BaseModel):
    holdings: Holdings
    tax_report: TaxReport
