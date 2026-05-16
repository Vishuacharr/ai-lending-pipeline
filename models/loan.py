"""Pydantic models for loan application data."""
from datetime import date
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


class EmploymentType(str, Enum):
    W2 = "W2"
    SELF_EMPLOYED = "SELF_EMPLOYED"
    INCOME_1099 = "1099"


class IncomePeriod(str, Enum):
    ANNUAL = "ANNUAL"
    MONTHLY = "MONTHLY"


class IncomeSource(str, Enum):
    W2 = "W2"
    PAYSTUB = "PAYSTUB"
    TAX_RETURN = "TAX_RETURN"


class LoanType(str, Enum):
    CONVENTIONAL = "CONVENTIONAL"
    FHA = "FHA"
    VA = "VA"


class PropertyType(str, Enum):
    SINGLE_FAMILY = "SINGLE_FAMILY"
    CONDO = "CONDO"
    MULTI_FAMILY = "MULTI_FAMILY"
    TOWNHOUSE = "TOWNHOUSE"


class Borrower(BaseModel):
    name: str
    ssn_last4: str = Field(pattern=r"^\d{4}$")
    annual_income_stated: float
    employment_type: EmploymentType


class Property(BaseModel):
    address: str
    appraised_value: float
    purchase_price: float
    property_type: PropertyType


class Income(BaseModel):
    source: IncomeSource
    reported_amount: float
    period: IncomePeriod
    employer: str


class LoanApplication(BaseModel):
    loan_id: str
    borrower: Borrower
    co_borrower: Optional[Borrower] = None
    property: Property
    loan_amount: float
    loan_type: LoanType
    interest_rate: float
    loan_term_years: int
    application_date: date
    closing_date: date
