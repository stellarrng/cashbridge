"""v7 financing data-quality, four-eyes assumptions, appeals, shared cases and worker failure paths."""
from datetime import date, timedelta, datetime, timezone
import sqlite3
import pytest
from pathlib import Path
from core.data_reliability import assess
from workspace.store import WorkspaceStore
from automation.engine import AutomationStore
from api.main import create_app
from tests.authed import RoleClient
from ui.backend_real import RealBackend
from scripts.run_demo_story import StoryClock


def meta(t, ident, days=0, verified=False):
    return {'type':t,'source_id':ident,'as_of':(date(2026,10,20)-timedelta(days=days)).isoformat(),
            'verified_by':'human_reviewer' if verified else 'unverified',
            'verified_at':'2026-10-20T01:00:00Z' if verified else ''}


def test_data_quality_blocks_missing_and_mismatched_and_stale():
    r=assess({'sources':[meta('ledger','a',200)],'ledger_entries':[{'reference':'A','amount':'3'}],
              'bank_entries':[{'reference':'A','amount':'5'}]}, date(2026,10,20))
    assert r['gate']=='BLOCKED_FOR_FINANCING'
    assert {'MISSING_SOURCE','STALE_SOURCE','RECONCILIATION_MISMATCH'} <= {i['code'] for i in r['issues']}
    assert 'prepare_draft' not in r['allowed_activities']
    assert not r['quality_index_is_probability']


def test_data_quality_complete_manifest_needs_real_independent_verification():
    sources=[meta(t,str(i),verified=True) for i,t in enumerate(('bank_statement','receivables_aging','ledger'))]
    r=assess({'sources':sources,'ledger_entries':[{'reference':'1','amount':'99.00'}],
              'bank_entries':[{'reference':'1','amount':'99.00'}]},date(2026,10,20))
    assert r['gate']=='REVIEW_REQUIRED'  # self-declared verification is not trusted
    assert not r['external_authenticity_verified']


def test_data_quality_fails_invalid_records_and_money():
    with pytest.raises(ValueError): assess({'ledger_entries':[{'reference':'A','amount':'NaN'}]})
    with pytest.raises(ValueError): assess({'ledger_entries':[{'reference':'A','amount':'1'},{'reference':'A','amount':'2'}]})


def test_request_requires_separate_actor_and_rejects_stale(tmp_path):
    s=WorkspaceStore(tmp_path/'ws.sqlite')
    first=s.propose('TEN1','case','preparer','marketing_usd','100','Marketing Q4')
    second=s.propose('TEN1','case','preparer2','marketing_usd','200','Marketing Q4')
    with pytest.raises(ValueError): s.review('TEN1',first['id'],'preparer',True,'agreed')
    s.review('TEN1',first['id'],'director',True,'approved new budget')
    with pytest.raises(ValueError,match='Stale'): s.review('TEN1',second['id'],'director',True,'approve again')
    assert s.assumptions('TEN1')['marketing_usd']=={'value':100.0,'version':1}
    assert s.assumptions('TEN2')=={}
    with pytest.raises(ValueError): s.review('TEN1',first['id'],'director',True,'retry')
    assert len(s.list_requests('TEN1','case')[0]['activities'])>=1


def test_correspondence_is_tenant_and_case_scoped(tmp_path):
    s=WorkspaceStore(tmp_path/'ws.sqlite')
    s.post_message('TEN1','case1','bank.lihua','bank_reviewer','evidence_request','Please provide shipping proof')
    assert len(s.list_messages('TEN1','case1'))==1
    assert s.list_messages('TEN2','case1')==[]
    assert s.list_messages('TEN1','case2')==[]


def test_queue_retries_transient_crashes_and_dead_letter(tmp_path,monkeypatch):
    store=AutomationStore(tmp_path/'queue.db')
    job=store.enqueue('support_triage',{'message':'Question'},'retry-test-0001')
    import automation.engine as eng
    def crash(kind,payload): raise OSError('provider disconnected')
    monkeypatch.setattr(eng,'evaluate',crash)
    one=store.run_pending()[0]
    assert one['state']=='pending' and one['attempts']==1 and one['retry_at']
    # Simulate the passage of backoff time in a fixture, not in production.
    with store._connect() as conn: conn.execute('UPDATE jobs SET next_run=NULL WHERE id=?',(job['id'],))
    two=store.run_pending()[0]
    assert two['state']=='pending' and two['attempts']==2
    with store._connect() as conn: conn.execute('UPDATE jobs SET next_run=NULL WHERE id=?',(job['id'],))
    three=store.run_pending()[0]
    assert three['state']=='dead_letter' and len(store.dead_letters())==1
    assert store.enqueue('support_triage',{'message':'Question'},'retry-test-0001')['id']==job['id']
    assert store.redrive(job['id'])['state']=='pending'
    assert store.dead_letters()==[]


def test_queue_reclaims_crashed_worker(tmp_path):
    store=AutomationStore(tmp_path/'queue.db')
    job=store.enqueue('cash_alert',{'projected_balances':[0],'minimum_reserve':100},'crash-test-0001')
    with store._connect() as conn:
        conn.execute("UPDATE jobs SET state='running',claimed_at='2020-01-01T00:00:00+00:00',attempts=1 WHERE id=?",(job['id'],))
    assert store.recover_stale()==1
    assert store.run_pending()[0]['state']=='needs_review'


@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setenv('CASHBRIDGE_WORKSPACE_DB',str(tmp_path/'workspace.db'))
    backend=RealBackend(runtime_dir=tmp_path/'runtime',clock=StoryClock())
    client=RoleClient(create_app(lambda: backend,dist_dir=tmp_path/'no-ui'))
    return client,backend


def test_backend_permissions_and_approved_scenario(api):
    client,backend=api
    assert client.post('/api/workspace/requests',json={'field':'marketing_usd','proposed_value':'15000','reason':'Planned campaign spending'},headers=client.header('sme.minh')).status_code==403
    r=client.post('/api/workspace/requests',json={'field':'marketing_usd','proposed_value':'15000','reason':'Planned campaign spending'})
    assert r.status_code==200,r.text
    id=r.json()['id']
    assert client.post(f'/api/workspace/requests/{id}/review',json={'approve':True,'note':'Budget approved'}).status_code==403
    assert client.post(f'/api/workspace/requests/{id}/review',json={'approve':True,'note':'Budget approved'},headers=client.header('sme.minh')).status_code==200
    case=client.post('/api/workspace/scenario',json={'available_cash_usd':20000,'minimum_reserve_usd':1000})
    assert case.status_code==200,case.text
    assert case.json()['funding_gap_usd']==0
    assert case.json()['breakdown_usd']['marketing']==15000
    assert case.json()['credit_decision_performed'] is False
    assert client.get('/api/workspace/requests',headers=client.header('bank.lihua')).status_code==403


def test_bank_messages_never_available_before_release(api):
    client,backend=api
    pack_id='not-published'
    assert client.get(f'/api/workspace/cases/{pack_id}/messages',headers=client.header('bank.lihua')).status_code==404
    assert client.post(f'/api/workspace/cases/{pack_id}/messages',json={'kind':'question','message':'Show invoices'},headers=client.header('bank.lihua')).status_code==404
    # Publish via the same existing controlled path as the standard bank test.
    assert client.post('/api/autopilot/run',json={'execute':True}).json()['decision']=='AWAITING_DIRECTOR_APPROVAL'
    client.post('/api/request_otp',headers=client.header('sme.minh'))
    published=client.post('/api/approve',json={'code':backend.coord.otp.current_code()},headers=client.header('sme.minh'))
    assert published.status_code==200,published.text
    pack_id=published.json()['snapshot']['pack']['pack_id']
    p=client.post(f'/api/workspace/cases/{pack_id}/messages',json={'kind':'evidence_request','message':'Provide invoice details'},headers=client.header('bank.lihua'))
    assert p.status_code==200,p.text
    assert p.json()['external_message_sent'] is False
    view=client.get(f'/api/workspace/cases/{pack_id}/messages')
    assert view.status_code==200,view.text
    assert view.json()['items'][0]['message']=='Provide invoice details'


def test_enforced_quality_gate_fails_closed_without_server_attestation(api, monkeypatch):
    client,backend=api
    monkeypatch.setenv('CASHBRIDGE_REQUIRE_DATA_GATE','1')
    monkeypatch.delenv('CASHBRIDGE_QUALITY_MANIFEST_PATH',raising=False)
    r=client.post('/api/autopilot/run',json={'execute':True})
    assert r.status_code==409
    assert 'manifest' in r.json()['detail']
    # Read-only plan remains available even if financial actions require quality verification.
    plan=client.post('/api/autopilot/run',json={'execute':False})
    assert plan.status_code==200


def test_offline_validation_does_not_claim_real_sme_generalisation(tmp_path):
    import csv
    from eval.external_validation import evaluate_csv
    data=tmp_path/'synthetic_eval.csv'
    with data.open('w',newline='') as handle:
        w=csv.writer(handle)
        w.writerow(['observed_at','defaulted','debt_ratio','days_late'])
        for i in range(180):
            month=i//15 + 1
            yr=2024 if month<=12 else 2025
            m=month if month<=12 else month-12
            w.writerow([f'{yr}-{m:02d}-{i%15+1:02d}',int(i%7<2),(i*7)%100/100,(i*3)%60])
    report=evaluate_csv(data,'defaulted','observed_at',['debt_ratio','days_late'])
    assert report['n_train']>report['n_test']>=25
    assert report['baseline_constant_prevalence']['brier']>=0
    assert report['generalizable_to_local_smes'] is False
    with pytest.raises(ValueError): evaluate_csv(data,'defaulted','observed_at',['defaulted'])
