"""Pydantic models for Closing Disclosure data."""
from typing import List
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class LineItemCategory(str, Enum):
    ORIGINATION = "ORIGINATION"
    SERVICES_BORROWER_SHOPPED = "SERVICES_BORROWER_SHOPPED"
    SERVICES_BORROWER_DID_NOT_SHOP = "SERVICES_BORROWER_DID_NOT_SHOP"
    TAXES_GOVT_FEES = "TAXES_GOVT_FEES"
    PREPAIDS = "PREPAIDS"
    INITIAL_ESCROW = "INITIAL_ESCROW"
    OTHER = "OTHER"


class LineItem(BaseModel):
    line_number: str
    description: str
    category: LineItemCategory
    amount: float
    payee: str


class ClosingDisclosure(BaseModel):
    loan_id: str
    closing_costs: List[LineItem] = Field(default_factory=list)
    loan_amount: float
    down_payment: float
    seller_credits: float = 0.0
    lender_credits: float = 0.0
    total_closing_costs: float = 0.0
    cash_to_close_stated: float = 0.0
    cash_to_close_computed: float = 0.0
    balance_check_passed: bool = False
    discrepancy_amount: float = 0.0

    @model_validator(mode="after")
    def compute_balance(self) -> "ClosingDisclosure":
        self.total_closing_costs = sum(item.amount for item in self.closing_costs)
        self.cash_to_close_computed = (
            self.loan_amount
            - self.down_payment
            + self.total_closing_costs
            - self.lender_credits
            - self.seller_credits
        )
        self.discrepancy_amount = abs(self.cash_to_close_computed - self.cash_to_close_stated)
        self.balance_check_passed = self.discrepancy_amount <= 0.50
        return self


class BalanceCheck(BaseModel):
    passed: bool
    stated_amount: float
    computed_amount: float
    discrepancy: float
    flagged_line_items: List[str] = Field(default_factory=list)
