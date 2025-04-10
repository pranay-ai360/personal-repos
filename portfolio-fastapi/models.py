# models.py
from pydantic import BaseModel, Field, validator, conlist, ConfigDict, root_validator
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Union, Dict, Any
from enum import Enum
import pytz
import uuid

# Define PHT timezone
PHT = pytz.timezone('Asia/Manila')

# --- Enums ---
class PortfolioStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"

class EventType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    CONVERT = "convert"
    SEND = "send"
    RECEIVE = "receive"
    REWARD = "reward"
    ADJUSTMENT = "adjustment"

# --- Helper Validator Function ---
@root_validator(pre=True, allow_reuse=True)
def validate_ensure_aware_and_consistent(cls, values: Dict[str, Any]) -> Dict[str, Any]:
    dt_utc_str_alias = values.get('datetime_utc')
    dt_pht_str_alias = values.get('datetime_pht')
    dt_utc: Optional[datetime] = None
    dt_pht: Optional[datetime] = None
    utc_parsed_ok = False
    pht_parsed_ok = False

    value_utc = dt_utc_str_alias
    if isinstance(value_utc, str):
        try:
            dt_utc = datetime.fromisoformat(value_utc.replace('Z', '+00:00'))
            if dt_utc.tzinfo is None: dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            else: dt_utc = dt_utc.astimezone(timezone.utc)
            utc_parsed_ok = True
        except (ValueError, TypeError) as e: raise ValueError(f"Invalid datetime_utc format ('{value_utc}'): {e}") from e
    elif isinstance(value_utc, datetime):
        dt_utc = value_utc
        if dt_utc.tzinfo is None: dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        else: dt_utc = dt_utc.astimezone(timezone.utc)
        utc_parsed_ok = True

    value_pht = dt_pht_str_alias
    if isinstance(value_pht, str):
        try:
            dt_pht = datetime.fromisoformat(value_pht.replace('Z', '+00:00'))
            if dt_pht.tzinfo is None: dt_pht = PHT.localize(dt_pht)
            else: dt_pht = dt_pht.astimezone(PHT)
            pht_parsed_ok = True
        except (ValueError, TypeError) as e: raise ValueError(f"Invalid datetime_pht format ('{value_pht}'): {e}") from e
    elif isinstance(value_pht, datetime):
         dt_pht = value_pht
         if dt_pht.tzinfo is None: dt_pht = PHT.localize(dt_pht)
         else: dt_pht = dt_pht.astimezone(PHT)
         pht_parsed_ok = True

    if not utc_parsed_ok and not pht_parsed_ok:
        raise ValueError('At least one of datetime_utc or datetime_pht must be provided and valid')

    if utc_parsed_ok and not pht_parsed_ok:
        if dt_utc: dt_pht = dt_utc.astimezone(PHT)
    elif pht_parsed_ok and not utc_parsed_ok:
        if dt_pht: dt_utc = dt_pht.astimezone(timezone.utc)
    elif utc_parsed_ok and pht_parsed_ok:
        if dt_utc and dt_pht:
            if abs((dt_utc - dt_pht.astimezone(timezone.utc)).total_seconds()) > 1:
                 raise ValueError(f"Provided/derived datetime_utc ({dt_utc.isoformat()}) and datetime_pht ({dt_pht.isoformat()}) are inconsistent.")

    values['datetime_utc_derived'] = dt_utc
    values['datetime_pht_derived'] = dt_pht
    # Clean up original alias fields if they were strings
    if isinstance(dt_utc_str_alias, str): values.pop('datetime_utc', None)
    if isinstance(dt_pht_str_alias, str): values.pop('datetime_pht', None)
    return values

# --- Portfolio Management Models ---
class PortfolioInfo(BaseModel):
    id: str
    status: PortfolioStatus

class ListPortfolioRequest(BaseModel):
    cpmID: str

class ListPortfolioResponse(BaseModel):
    cpmID: str
    combinedPortfolio: Optional[PortfolioInfo] = None
    assetPortfolio: Dict[str, List[PortfolioInfo]] = Field(default_factory=dict)

class CreateCombinedPortfolioRequest(BaseModel):
    cpmID: str

class CreateCombinedPortfolioResponse(BaseModel):
    cpmID: str
    combinedPortfolioId: str

class CreateAssetPortfolioRequest(BaseModel):
    cpmID: str
    assetPortfolio: conlist(str, min_length=1)

class CreateAssetPortfolioResponseItem(BaseModel):
    id: str
    status: PortfolioStatus = PortfolioStatus.ACTIVE

class CreateAssetPortfolioResponse(BaseModel):
    cpmID: str
    assetPortfolio: Dict[str, List[CreateAssetPortfolioResponseItem]]

# --- Event and Price Models (API Layer) ---

class PriceData(BaseModel):
    datetime_utc: Optional[Union[str, datetime]] = Field(None, description="Optional: Timestamp in UTC (ISO 8601 format)")
    datetime_pht: Optional[Union[str, datetime]] = Field(None, description="Optional: Timestamp in PHT (ISO 8601 format)")
    pair: str
    price: float
    datetime_utc_derived: Optional[datetime] = Field(None, exclude=True)
    datetime_pht_derived: Optional[datetime] = Field(None, exclude=True)
    _validate_datetimes = validate_ensure_aware_and_consistent
    model_config = ConfigDict(populate_by_name=True, extra='ignore')

class EventData(BaseModel):
    assetPortfolioID: str
    orderID: Optional[str] = None
    pair: str
    datetime_utc: Optional[Union[str, datetime]] = Field(None, description="Optional: Timestamp in UTC (ISO 8601 format)")
    datetime_pht: Optional[Union[str, datetime]] = Field(None, description="Optional: Timestamp in PHT (ISO 8601 format)")
    event: EventType
    quantity: float
    value: float = Field(..., alias="totalValue")
    datetime_utc_derived: Optional[datetime] = Field(None, exclude=True)
    datetime_pht_derived: Optional[datetime] = Field(None, exclude=True)
    _validate_datetimes = validate_ensure_aware_and_consistent
    model_config = ConfigDict(populate_by_name=True, extra='ignore')

# --- Query and Generate Models (API Layer) ---

class QueryRequest(BaseModel):
    cpmID: str
    assetPortfolioID: conlist(str, min_length=1) = Field(..., alias="assetPortfolioID")
    start_datetime_utc: datetime = Field(..., description="Start timestamp (inclusive, UTC, ISO 8601)")
    end_datetime_utc: datetime = Field(..., description="End timestamp (inclusive, UTC, ISO 8601)")

    @validator('start_datetime_utc', 'end_datetime_utc', pre=True, allow_reuse=True)
    def ensure_utc(cls, v):
        if isinstance(v, str):
            try: dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError: raise ValueError("Invalid datetime format.")
        elif isinstance(v, datetime): dt = v
        else: raise TypeError("datetime must be string or datetime")
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        elif dt.tzinfo != timezone.utc: dt = dt.astimezone(timezone.utc)
        return dt
    @validator('end_datetime_utc')
    def end_date_after_start_date(cls, v, values):
        if 'start_datetime_utc' in values and v < values['start_datetime_utc']:
            raise ValueError('end_datetime_utc must be >= start_datetime_utc')
        return v
    model_config = ConfigDict(populate_by_name=True)

class GenerateRequest(BaseModel):
    assetPortfolioID: conlist(str, min_length=1) = Field(..., alias="assetPortfolioID")
    model_config = ConfigDict(populate_by_name=True)

class GenerateResponse(BaseModel):
    status: str = "Portfolio generation initiated in background."
    details: Optional[str] = None

# --- Response Models ---
class StatusResponse(BaseModel):
    status: str = "Accepted"
    message: Optional[str] = None

class PortfolioItem(BaseModel):
    datetime_pht: datetime = Field(..., alias="datetime_pht")
    aum: float = Field(..., alias="AUM")
    avg_cost: float = Field(..., alias="AVG_cost")
    unrealised_value: Optional[float] = Field(None, alias="Unrealised_Value")
    realised_value: float = Field(..., alias="Realised_Value")
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

class PortfolioQueryResultItem(BaseModel):
    cpmID: str
    pair: str
    assetPortfolioID: str
    status: PortfolioStatus
    start_datetime_pht: datetime
    end_datetime_pht: datetime
    portfolio: List[Union[PortfolioItem, dict]] = Field([])

QueryResponse = List[PortfolioQueryResultItem]