"""Pydantic models for TRID compliance checks."""
from datetime import date
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class ToleranceBucket(str, Enum):
    ZERO_TOLERANCE = "ZERO_TOLERANCE"
    TEN_PERCENT = "TEN_PERCENT"
    NO_LIMIT = "NO_LIMIT"


class TRIDCheck(BaseModel):
    check_id: str
    rule_name: str
    passed: bool
    details: str
    bucket: Optional[ToleranceBucket] = None
    variance_amount: Optional[float] = None


class DisclosureTimeline(BaseModel):
    loan_estimate_date: date
    closing_disclosure_date: date
    closing_date: date
    le_to_cd_days: int = 0
    cd_to_close_days: int = 0
    timeline_valid: bool = False

    @model_validator(mode="after")
    def compute_days(self) -> "DisclosureTimeline":
        self.le_to_cd_days = (self.closing_disclosure_date - self.loan_estimate_date).days
        self.cd_to_close_days = (self.closing_date - self.closing_disclosure_date).days
        self.timeline_valid = self.cd_to_close_days >= 3
        return self


class ToleranceResult(BaseModel):
    bucket: ToleranceBucket
    le_amount: float
    cd_amount: float
    variance: float = Field(default=0.0)
    tolerance_limit: float
    within_tolerance: bool = False

    @model_validator(mode="after")
    def compute_variance(self) -> "ToleranceResult":
        self.variance = self.cd_amount - self.le_amount
        if self.bucket == ToleranceBucket.ZERO_TOLERANCE:
            self.within_tolerance = self.variance <= 0.0
        elif self.bucket == ToleranceBucket.TEN_PERCENT:
            pct = (self.variance / self.le_amount * 100) if self.le_amount > 0 else 0
            self.within_tolerance = pct <= self.tolerance_limit
        else:
            self.within_tolerance = True
        return self
