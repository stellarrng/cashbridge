import copy
from automation.engine import AutomationStore, evaluate
from automation.audit_evidence import verify_evidence
from fastapi.testclient import TestClient
from api.main import create_app


def test_accounting_highlights_and_sha256(tmp_path):
    data={'ledger':[{'reference':'A','amount':'120.00'}, {'reference':'B','amount':'30'}],
          'bank':[{'reference':'A','amount':'100.00'}, {'reference':'C','amount':'5'}]}
    out=evaluate('accounting_reconcile',data)
    assert len(out['highlights']) == 3
    assert out['highlights'][0]['field']=='amount'
    assert out['highlights'][0]['difference']=='20.00'
    store=AutomationStore(tmp_path/'test.db')
    job=store.enqueue('accounting_reconcile',data,'accounting-record-01')
    assert store.run_pending()[0]['state']=='needs_review'
    import pytest
    with pytest.raises(ValueError): store.review_audit(job['id'],'auditor-1','accepted')
    response=store.review_audit(job['id'],'auditor-1','accepted_with_exceptions')
    assert response['verified'] and len(response['sha256'])==64
    evidence=store.get_audit_seal(job['id'])['seal']
    assert verify_evidence(evidence)
    copy_evidence=copy.deepcopy(evidence)
    copy_evidence['evidence']['source']['ledger'][0]['amount']='1.00'
    assert not verify_evidence(copy_evidence)
    with pytest.raises(ValueError): store.review_audit(job['id'],'auditor-1','rejected')


def test_invoice_flags_and_no_fraud_conclusion():
    out=evaluate('audit_invoice',{'invoices':[{'invoice_number':'A','vendor':'Firm','amount':'20'},
                                                 {'invoice_number':'A','vendor':'Firm','amount':'20'}]})
    assert out['fraud_conclusion']=='not_determined'
    assert out['highlights'][0]['reason']=='potential_duplicate'


def test_api_fail_closed(monkeypatch,tmp_path):
    monkeypatch.delenv('CASHBRIDGE_AUTOMATION_TOKEN',raising=False)
    client=TestClient(create_app())
    assert client.get('/api/automation/jobs').status_code==503
    monkeypatch.setenv('CASHBRIDGE_AUTOMATION_TOKEN','test-only-secret')
    monkeypatch.setenv('CASHBRIDGE_AUTOMATION_DB',str(tmp_path/'db.sqlite'))
    assert client.get('/api/automation/jobs',headers={'Authorization':'Bearer wrong'}).status_code==403
    assert client.get('/api/automation/jobs',headers={'Authorization':'Bearer test-only-secret'}).status_code==200
    response=client.post('/api/automation/jobs',headers={'Authorization':'Bearer test-only-secret'},json={
         'kind':'accounting_reconcile','payload':{'ledger':[],'bank':[]},'idempotency_key':'audit-sample-123'})
    assert response.status_code==200
    assert client.post('/api/automation/audit/'+response.json()['id']+'/review',json={'reviewer_id':'auditor','decision':'accepted'},headers={'Authorization':'Bearer test-only-secret'}).status_code in (401,403,503)


def test_highlight_edited_and_model_generated_numbers(tmp_path):
    from automation.audit_evidence import provenance_highlights
    import pytest
    edits = [
        {'document_id':'inv-19','field':'total','old_value':'100.00','new_value':'125.00',
         'origin':'human_edit','actor_id':'accountant-1','source_reference':'invoice-line-8'},
        {'document_id':'cash-forecast','field':'week_7_cash','old_value':'1000.00','new_value':'880.00',
         'origin':'ml_prediction','method':'buyer_risk_v1','source_reference':'model-run-17'},
        {'document_id':'budget-1','field':'allocated','new_value':'500.00',
         'origin':'ai_suggestion','method':'budget_assistant_v1'},
    ]
    flagged = provenance_highlights(edits)
    assert flagged[0]['delta']=='25.00' and flagged[0]['color_hint']=='blue'
    assert flagged[1]['origin']=='ml_prediction' and flagged[1]['color_hint']=='purple'
    assert flagged[2]['status']=='requires_review'
    result=evaluate('provenance_review',{'changes':edits})
    assert result['values_applied'] is False and result['review_required']
    store=AutomationStore(tmp_path/'provenance.db')
    job=store.enqueue('provenance_review',{'changes':edits},'change-review-001')
    assert store.run_pending()[0]['state']=='needs_review'
    seal=store.review_audit(job['id'],'accountant-1','accepted_with_exceptions')
    assert seal['verified']
    with pytest.raises(ValueError):
        provenance_highlights([{'document_id':'a','field':'amount','new_value':'NaN','origin':'ai_suggestion','method':'fake'}])
    with pytest.raises(ValueError):
        provenance_highlights([{'document_id':'a','field':'amount','new_value':'50','origin':'human_edit'}])
