"""Pydantic models for loan documents."""
from datetime import datetime
from typing import Any, Dict, List
from enum import Enum
from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    W2 = "W2"
    PAYSTUB = "PAYSTUB"
    TAX_RETURN_1040 = "TAX_RETURN_1040"
    APPRAISAL_REPORT = "APPRAISAL_REPORT"
    CLOSING_DISCLOSURE = "CLOSING_DISCLOSURE"
    LOAN_ESTIMATE = "LOAN_ESTIMATE"
    PURCHASE_CONTRACT = "PURCHASE_CONTRACT"
    TITLE_COMMITMENT = "TITLE_COMMITMENT"
    UNKNOWN = "UNKNOWN"


class Document(BaseModel):
    doc_id: str
    doc_type: DocumentType
    filename: str
    upload_timestamp: datetime
    version: int = 1
    data: Dict[str, Any] = Field(default_factory=dict)


class DocumentVersion(BaseModel):
    doc_id: str
    versions: List[Document]
    current_version: int = 1


class ClassificationResult(BaseModel):
    doc_id: str
    classified_type: DocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    routing_target: str
