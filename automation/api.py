"""Authenticated task queue API, opt-in; deploy behind TLS and real identity provider."""
from __future__ import annotations
import hmac
import os
from pathlib import Path
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from .engine import AutomationStore, KINDS

router = APIRouter(prefix='/api/automation', tags=['local-cloud-automation'])


def auth(authorization: str | None, require_reviewer: bool=False):
    secret = os.environ.get('CASHBRIDGE_AUTOMATION_TOKEN','')
    reviewer_secret = os.environ.get('CASHBRIDGE_AUDIT_REVIEWER_TOKEN','') if require_reviewer else secret
    if not secret or not reviewer_secret or not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(503 if not secret else 401, 'Automation authentication unavailable or required')
    if not hmac.compare_digest(authorization[7:].encode(), reviewer_secret.encode()):
        raise HTTPException(403,'Insufficient authorization')


def store():
    return AutomationStore(Path(os.getenv('CASHBRIDGE_AUTOMATION_DB','data/automation_jobs.sqlite3')))

class JobBody(BaseModel):
    kind: str
    payload: dict
    idempotency_key: str = Field(min_length=8,max_length=128)

class ReviewBody(BaseModel):
    reviewer_id: str = Field(min_length=1,max_length=100)
    decision: str

@router.post('/jobs')
def enqueue(body: JobBody, authorization: str | None = Header(default=None)):
    auth(authorization)
    try:
        return store().enqueue(body.kind,body.payload,body.idempotency_key)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422,str(exc)) from exc

@router.get('/jobs')
def jobs(authorization: str | None = Header(default=None)):
    auth(authorization)
    return store().list_jobs()

@router.post('/audit/{job_id}/review')
def audit_review(job_id: str, body:ReviewBody,authorization: str | None = Header(default=None)):
    auth(authorization,require_reviewer=True)
    try:
        return store().review_audit(job_id,body.reviewer_id,body.decision)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc

@router.get('/audit/{job_id}/evidence')
def audit_evidence(job_id: str,authorization: str | None = Header(default=None)):
    auth(authorization,require_reviewer=True)
    try:
        return store().get_audit_seal(job_id)
    except ValueError as exc:
        raise HTTPException(404,str(exc)) from exc
