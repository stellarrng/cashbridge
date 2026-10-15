"""
Pydantic v2 schemas for Agent orchestration, L0-L4 permission audit logs,
BEC fraud detection, and tool call envelopes.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from config.settings import PermissionLevel


class PermissionAuditLog(BaseModel):
    log_id: str
    timestamp_utc: str
    permission_level: PermissionLevel
    action_name: str
    actor: str = "SYSTEM_AGENT"
    target_resource: str
    state_hash: str
    status: str = Field(..., description="'APPROVED' | 'BLOCKED' | 'REQUIRES_OTP' | 'OTP_CONFIRMED'")
    reason: str
    human_otp_verified: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class ToolCallEnvelope(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    permission_level: PermissionLevel
    requires_otp: bool = False
    is_hard_blocked: bool = False
    execution_result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class BECScanResult(BaseModel):
    email_id: str
    sender_email: str
    sender_domain: str
    is_spoofed_domain: bool = False
    detected_suspicious_keywords: List[str] = Field(default_factory=list)
    flagged_bank_change: bool = False
    extracted_swift: Optional[str] = None
    extracted_iban: Optional[str] = None
    threat_level: str = Field(..., description="'SAFE' | 'MEDIUM' | 'CRITICAL_BLOCK'")
    reason: str
    sanitized_text: str


class CFOAssistantQuery(BaseModel):
    prompt: str
    context_keys: List[str] = Field(default_factory=list)
    demo_mode: bool = True


class CFOAssistantResponse(BaseModel):
    response_text: str
    cited_deterministic_metrics: Dict[str, Any] = Field(default_factory=dict)
    active_permission: PermissionLevel
    scenario_adjustments: Optional[Dict[str, Any]] = None
    evidence_bundle_hash: Optional[str] = None


class VerifiableFundingPackData(BaseModel):
    pack_id: str
    invoice_id: str
    buyer_name: str
    buyer_country: str
    gross_amount_usd: float
    advance_amount_requested_usd: float
    financing_partner: str
    document_bundle_sha256: str
    audit_block_index: int
    created_at_utc: str
    otp_approved_by: str
    pdf_filepath: str
