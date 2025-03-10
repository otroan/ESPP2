"""Data models for espp2"""

# pylint: disable=too-few-public-methods, missing-class-docstring, no-name-in-module
# pylint: disable=no-self-argument

from datetime import date
from typing import List, Literal, Annotated, Union, Optional, Any, Dict
from enum import Enum
from decimal import Decimal
from pydantic import (
    field_validator,
    model_validator,
    ConfigDict,
    BaseModel,
    validator,
    Field,
    RootModel,
)
from espp2.fmv import FMV

#
# Transactions data model
#
#########################################################################

# Singleton caching stock and currency data
fmv = FMV()


class EntryTypeEnum(str, Enum):
    """Entry type"""

    BUY = "BUY"
    DEPOSIT = "DEPOSIT"
    TAX = "TAX"
    TAXSUB = "TAXSUB"
    DIVIDEND = "DIVIDEND"
    DIVIDEND_REINV = "DIVIDEND_REINV"
    WIRE = "WIRE"
    SELL = "SELL"
    TRANSFER = "TRANSFER"
    FEE = "FEE"
    CASHADJUST = "CASHADJUST"

    def __str__(self):
        return self.value


class Amount(BaseModel):
    """Amount represents a monetary value in a specific currency with lazy conversion capabilities"""

    currency: str
    value: Decimal
    _exchange_rates: Dict[str, Decimal] = {}
    _converted_values: Dict[str, Decimal] = {}
    amountdate: Optional[date] = None
    legacy_nok_rate: Optional[Decimal] = None

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_format(cls, values):
        """Handle legacy format that includes nok_exchange_rate and nok_value"""
        if isinstance(values, dict) and "nok_exchange_rate" in values:
            return {
                "currency": values["currency"],
                "value": Decimal(values["value"]),
                "legacy_nok_rate": Decimal(values["nok_exchange_rate"]),
                "amountdate": values.get("amountdate", None),
            }
        return values

    def get_in(self, target_currency: str) -> Decimal:
        """Get the amount in the target currency"""
        if target_currency == self.currency:
            return self.value
        # Handle legacy USD-NOK conversion
        if self.legacy_nok_rate is not None:
            if self.currency == "USD" and target_currency == "NOK":
                return self.value * self.legacy_nok_rate
            if self.currency == "NOK" and target_currency == "USD":
                return self.value / self.legacy_nok_rate

        # For all other conversions, require a date
        if self.amountdate is None:
            raise ValueError(
                f"Cannot convert {self.currency} to {target_currency} without a date"
            )

        if target_currency not in self._converted_values:
            rate = self._get_exchange_rate(target_currency)
            self._converted_values[target_currency] = self.value * rate

        return self._converted_values[target_currency]

    def _get_exchange_rate(self, target_currency: str) -> Decimal:
        """Get exchange rate for target currency (with caching)"""
        if target_currency not in self._exchange_rates:
            self._exchange_rates[target_currency] = fmv.get_currency(
                self.currency, self.amountdate, target_currency
            )
        return self._exchange_rates[target_currency]

    @property
    def nok_value(self) -> Decimal:
        """Convenience property for NOK conversion (maintained for compatibility)"""
        return self.get_in("NOK")

    @property
    def nok_exchange_rate(self) -> Decimal:
        """Convenience property for NOK conversion (maintained for compatibility)"""
        if self.amountdate is None and self.legacy_nok_rate is not None:
            return self.legacy_nok_rate
        return self._get_exchange_rate("NOK")

    def __str__(self):
        """String representation with currency symbol"""
        symbols = {
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            # Add more currency symbols as needed
        }
        symbol = symbols.get(self.currency, self.currency)
        return f"{symbol}{self.value} ({self.amountdate})"

    def __format__(self, format_spec: str) -> str:
        """Format the amount. Delegates to __str__ if no format specified"""
        if format_spec == "":
            return f"{self.value}"
        # Handle specific format specs if needed
        return format(self.value, format_spec)

    def __mul__(self, qty: Decimal) -> "Amount":
        """Multiply amount by a quantity"""
        result = self.model_copy()
        result.value *= qty
        # Scale any existing converted values
        result._converted_values = {
            curr: value * qty for curr, value in self._converted_values.items()
        }
        return result

    def __add__(self, other: "Amount") -> "Amount":
        """Add two amounts (must be same currency)"""
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot add different currencies: {self.currency} and {other.currency}"
            )

        result = self.model_copy()
        result.value += other.value

        # Combine converted values where both amounts have them
        result._converted_values = {}
        for currency in set(self._converted_values) & set(other._converted_values):
            result._converted_values[currency] = (
                self._converted_values[currency] + other._converted_values[currency]
            )

        return result

    def __sub__(self, other: "Amount") -> "Amount":
        """Subtract two amounts (must be same currency)"""
        # Check if self.currency or other.currency are ESPPUSD and USD.
        # Then allow the subtraction.
        if (
            not (self.currency == "ESPPUSD" and other.currency == "USD")
            and not (self.currency == "USD" and other.currency == "ESPPUSD")
            and self.currency != other.currency
        ):
            raise ValueError(
                f"Cannot subtract different currencies: {self.currency} and {other.currency}"
            )

        result = self.model_copy()
        result.value -= other.value

        # Combine converted values where both amounts have them
        result._converted_values = {}
        for currency in set(self._converted_values) & set(other._converted_values):
            result._converted_values[currency] = (
                self._converted_values[currency] - other._converted_values[currency]
            )

        return result

    def __radd__(self, other) -> "Amount":
        """Support sum() operation"""
        if isinstance(other, int) and other == 0:
            return self
        return self.__add__(other)

    @classmethod
    def zero(cls, currency: str = "USD") -> "Amount":
        """Create a zero amount in the specified currency"""
        return cls(currency=currency, value=Decimal("0"))

    def convert_to(self, target_currency: str) -> "Amount":
        """Create a new Amount instance in the target currency"""
        if target_currency == self.currency:
            return self.model_copy()

        return Amount(
            currency=target_currency,
            value=self.get_in(target_currency),
            amountdate=self.amountdate,
        )


class PositiveAmount(Amount):
    """Positive amount"""

    # @field_validator("value", "nok_value")
    @classmethod
    def value_validator(cls, v):
        """Validate value"""
        if v < 0:
            raise ValueError("Negative value", v)
        return v


class NegativeAmount(Amount):
    """Negative amount"""

    # @field_validator("value", "nok_value")
    @classmethod
    def value_validator(cls, v):
        """Validate value"""
        if v > 0:
            raise ValueError("Must be negative value", v)
        return v


class GainAmount(BaseModel):
    """Represents a gain/loss between two Amount instances, handling both USD and NOK calculations"""

    value: Decimal  # USD gain/loss
    nok_buy_value: Decimal  # Original NOK cost basis
    nok_sell_value: Decimal  # NOK value of sale
    nok_value: Decimal  # Total NOK gain/loss

    @classmethod
    def from_amounts(cls, sell_amount: Amount, buy_amount: Amount):
        """Calculate gain from sell and buy amounts"""
        return cls(
            value=sell_amount.value - buy_amount.value,
            nok_buy_value=buy_amount.nok_value,
            nok_sell_value=sell_amount.nok_value,
            nok_value=sell_amount.nok_value - buy_amount.nok_value,
        )

    def __mul__(self, qty: Decimal) -> "GainAmount":
        """Allow multiplication by quantity"""
        return GainAmount(
            value=self.value * qty,
            nok_buy_value=self.nok_buy_value * qty,
            nok_sell_value=self.nok_sell_value * qty,
            nok_value=self.nok_value * qty,
        )


duplicates = {}


def get_id(values: Dict[str, Any]):
    """Get id"""
    d = values.source + str(values.date)
    if d in duplicates:
        duplicates[d] += 1
    else:
        duplicates[d] = 1

    id = f"{values.type} {str(values.date)}"
    try:
        if values.qty:
            id += " " + str(values.qty)
    except AttributeError:
        pass
    return id + ":" + str(duplicates[d])


class TransactionEntry(BaseModel):
    @model_validator(mode="after")
    @classmethod
    def validate_id(cls, v, info):
        """Validate id"""
        v.id = get_id(v)
        return v


class Buy(TransactionEntry):
    """Buy transaction"""

    type: Literal[EntryTypeEnum.BUY] = Field(default=EntryTypeEnum.BUY)
    date: date
    symbol: str
    qty: Decimal
    purchase_price: Amount
    source: str
    id: str = Optional[str]

    @field_validator("purchase_price")
    @classmethod
    def purchase_price_validator(cls, v, values):
        """Validate purchase price"""
        if v.nok_value < 0 or v.value < 0:
            raise ValueError("Negative values for purchase price", v, values)
        return v

    model_config = ConfigDict(extra="allow")


class Deposit(TransactionEntry):
    """Deposit transaction"""

    type: Literal[EntryTypeEnum.DEPOSIT] = Field(default=EntryTypeEnum.DEPOSIT)
    date: date
    qty: Decimal
    symbol: str
    description: str
    purchase_price: Amount
    purchase_date: Optional[date] = None
    discounted_purchase_price: Optional[Amount] = None
    source: str
    id: str = Optional[str]

    model_config = ConfigDict(extra="allow")


class Tax(TransactionEntry):
    """Tax withheld transaction"""

    type: Literal[EntryTypeEnum.TAX] = Field(default=EntryTypeEnum.TAX)
    date: date
    symbol: str
    description: str
    amount: NegativeAmount
    source: str
    id: str = Optional[str]


class Taxsub(TransactionEntry):
    """Tax returned transaction"""

    type: Literal[EntryTypeEnum.TAXSUB] = Field(default=EntryTypeEnum.TAXSUB)
    date: date
    symbol: str
    description: str
    amount: Amount
    source: str
    id: str = Optional[str]


class Dividend(TransactionEntry):
    """Dividend transaction"""

    type: Literal[EntryTypeEnum.DIVIDEND] = Field(default=EntryTypeEnum.DIVIDEND)
    date: date
    symbol: str
    amount: Optional[PositiveAmount] = None
    amount_ps: Optional[PositiveAmount] = None
    source: str
    id: str = Optional[str]

    @model_validator(mode="before")
    @classmethod
    def check_dividend_data(cls, values):
        """Lookup dividend data from the external API and put those records in the data model"""
        values["exdate"], values["declarationdate"], values["dividend_dps"] = (
            fmv.get_dividend(values["symbol"], values["date"])
        )
        return values

    model_config = ConfigDict(extra="allow")


class Dividend_Reinv(TransactionEntry):
    """Dividend reinvestment transaction"""

    type: Literal[EntryTypeEnum.DIVIDEND_REINV] = Field(
        default=EntryTypeEnum.DIVIDEND_REINV
    )
    date: date
    symbol: str
    amount: Amount
    description: str
    source: str
    id: str = Optional[str]


class Wire(TransactionEntry):
    """Wire transaction"""

    type: Literal[EntryTypeEnum.WIRE] = Field(default=EntryTypeEnum.WIRE)
    date: date
    amount: Amount
    description: str
    fee: Optional[NegativeAmount] = None
    source: str
    id: str = Optional[str]


class Sell(TransactionEntry):
    """Sell transaction"""

    type: Literal[EntryTypeEnum.SELL] = Field(default=EntryTypeEnum.SELL)
    date: date
    symbol: str
    qty: Annotated[Decimal, Field(lt=0)]
    fee: Optional[NegativeAmount] = None
    amount: Amount  # Net amount after fees
    description: str
    source: str
    id: str = Optional[str]


class Fee(TransactionEntry):
    """Independent Fee"""

    type: Literal[EntryTypeEnum.FEE] = Field(default=EntryTypeEnum.FEE)
    date: date
    amount: NegativeAmount
    source: str
    id: str = Optional[str]


class Transfer(TransactionEntry):
    """Transfer transaction"""

    type: Literal[EntryTypeEnum.TRANSFER] = Field(default=EntryTypeEnum.TRANSFER)
    date: date
    symbol: str
    qty: Decimal
    # amount: Amount
    fee: Optional[NegativeAmount] = 0
    source: str
    id: str = Optional[str]


class Cashadjust(TransactionEntry):
    """Adjust the cash-balance with a positive or negative adjustment"""

    type: Literal[EntryTypeEnum.CASHADJUST] = Field(default=EntryTypeEnum.CASHADJUST)
    date: date
    amount: Amount
    description: str
    source: str
    id: str = Optional[str]


Entry = Annotated[
    Union[
        Buy,
        Deposit,
        Tax,
        Taxsub,
        Dividend,
        Dividend_Reinv,
        Wire,
        Sell,
        Transfer,
        Fee,
        Cashadjust,
    ],
    Field(discriminator="type"),
]


class Transactions(BaseModel):
    """Transactions"""

    fromdate: date = None
    todate: date = None
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
    """Stock positions"""

    symbol: str
    date: date
    qty: Decimal
    tax_deduction: Decimal
    purchase_price: Amount

    @field_validator("purchase_price", mode="before")
    @classmethod
    def set_purchase_price(cls, value, info):
        """Set purchase price and calculate nok value if needed"""
        if isinstance(value, Amount):
            return value
        if "amountdate" not in value:
            value["amountdate"] = info.data["date"]
        if "nok_exchange_rate" not in value:
            return Amount(
                amountdate=info.data["date"],
                currency=value["currency"],
                value=value["value"],
            )
        return value

    model_config = ConfigDict(extra="allow")


class CashEntry(BaseModel):
    """Cash entry"""

    date: date
    description: str
    amount: Amount
    transfer: Optional[bool] = False

    @model_validator(mode='before')
    @classmethod
    def prepare_amount(cls, values):
        """Ensure amount has the correct date during initialization"""
        if isinstance(values, dict):
            if 'amount' in values and 'date' in values:
                if isinstance(values['amount'], dict):
                    values['amount']['amountdate'] = values['date']
        return values

    model_config = ConfigDict(extra="allow")


class Holdings(BaseModel):
    """Stock holdings"""

    year: int
    broker: str
    stocks: list[Stock]
    cash: list[CashEntry]

    def sum_qty(self):
        """Sum the quantity of all stocks"""
        return sum(stock.qty for stock in self.stocks)


class EOYBalanceItem(BaseModel):
    """EOY balance item"""

    symbol: str
    qty: Decimal
    amount: Amount
    fmv: Decimal
    model_config = ConfigDict(extra="allow")


class NativeAmount(BaseModel):
    """Represents monetary values in their native currencies without conversion capabilities"""

    values: Dict[str, Decimal]

    def __init__(self, **kwargs):
        """Initialize from currency_value keyword arguments (e.g., usd_value=100)"""
        values = {}
        # If values dict is provided directly, use it
        if "values" in kwargs:
            values = kwargs["values"]
        else:
            # Otherwise parse currency_value keyword arguments
            for key, value in kwargs.items():
                if key.endswith("_value"):
                    currency = key[:-6].upper()
                    values[currency] = Decimal(str(value))
        super().__init__(values=values)

    def __getattr__(self, name: str) -> Decimal:
        """Dynamic currency value access (e.g., usd_value, nok_value)"""
        if name.endswith("_value"):
            currency = name[:-6].upper()
            if currency not in self.values:
                raise ValueError(f"No value stored for currency {currency}")
            return self.values[currency]
        raise AttributeError(f"'NativeAmount' has no attribute '{name}'")

    def __add__(self, other: "NativeAmount") -> "NativeAmount":
        """Add two NativeAmount instances together"""
        result = {}
        # Add values from self
        for curr, val in self.values.items():
            result[curr] = val
        # Add values from other, combining where currencies match
        for curr, val in other.values.items():
            if curr in result:
                result[curr] += val
            else:
                result[curr] = val
        return NativeAmount(values=result)

    def __str__(self):
        return ", ".join(f"{curr}{val}" for curr, val in self.values.items())

class EOYDividend(BaseModel):
    """EOY dividend"""

    symbol: str
    amount: NativeAmount
    gross_amount: NativeAmount
    post_tax_inc_amount: Optional[NativeAmount] = None
    tax: NativeAmount  # Negative
    tax_deduction_used: Decimal  # NOK


class SalesPosition(BaseModel):
    """Sales positions"""

    symbol: str
    qty: Decimal
    sale_price: Amount
    purchase_price: Amount
    purchase_date: date
    gain_ps: GainAmount
    tax_deduction_used: Decimal


class EOYSales(BaseModel):
    """EOY sales"""

    symbol: str
    date: date
    qty: Decimal
    amount: Amount
    fee: Optional[Amount] = None
    from_positions: list[SalesPosition]
    totals: Optional[dict] = None
    # total_gain: Amount


class TaxReport(BaseModel):
    """Tax report"""

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
    """Cash model"""

    cash: List[CashEntry] = []


class ForeignShares(BaseModel):
    """Foreign shares"""

    symbol: str
    isin: str
    country: str
    account: str
    shares: Decimal
    wealth: Annotated[Decimal, Field(ge=0)]
    # Share of taxable dividend after October 6 2022.
    post_tax_inc_dividend: Optional[
        Annotated[Decimal, Field(ge=0, decimal_places=0)]
    ] = None
    # Taxable dividend
    dividend: Annotated[Decimal, Field(ge=0, decimal_places=0)]
    taxable_gain: Annotated[Decimal, Field(decimal_places=0)]
    taxable_post_tax_inc_gain: Optional[Annotated[Decimal, Field(decimal_places=0)]] = (
        None
    )
    tax_deduction_used: Annotated[Decimal, Field(ge=0, decimal_places=0)]


class CreditDeduction(BaseModel):
    """Credit deduction"""

    symbol: str
    country: str
    income_tax: Annotated[Decimal, Field(ge=0, decimal_places=0)]
    gross_share_dividend: Annotated[Decimal, Field(ge=0, decimal_places=0)]
    tax_on_gross_share_dividend: Annotated[Decimal, Field(ge=0, decimal_places=0)]


class TransferRecord(BaseModel):
    """Transfers"""

    date: date
    amount_sent: Annotated[Decimal, Field(ge=0, decimal_places=0)]
    amount_received: Annotated[Decimal, Field(gt=0, decimal_places=0)]
    gain: Annotated[Decimal, Field(decimal_places=0)]
    description: str


class CashSummary(BaseModel):
    """Cash account"""

    transfers: list[TransferRecord]
    remaining_cash: Amount
    holdings: list[CashEntry]
    gain: Decimal


class TaxSummary(BaseModel):
    """Tax summary"""

    year: int
    foreignshares: list[ForeignShares]
    credit_deduction: list[CreditDeduction]
    cashsummary: CashSummary


class ESPPResponse(BaseModel):
    """ESPP response"""

    zip: str
    tax_report: TaxReport
    summary: TaxSummary
    holdings: Holdings
    log: str
