"""The Word export is an unsigned template, never a signed legal contract."""
from io import BytesIO
from docx import Document
from fastapi.testclient import TestClient
from api.main import create_app
from tests.authed import RoleClient
from ui.backend_real import RealBackend
from scripts.run_demo_story import StoryClock


def test_docx_export_returns_unsigned_valid_word_document(tmp_path):
    backend=RealBackend(runtime_dir=tmp_path/'runtime',clock=StoryClock())
    client=RoleClient(create_app(lambda:backend,dist_dir=tmp_path/'none'))
    response=client.post('/api/contracts/draft-docx', json={'data':{
        'supplier':'Synthetic Supplier', 'customer':'Synthetic Customer',
        'scope':'Deliver 20 synthetic sample desks', 'amount':200000, 'contract_type':'supply'}})
    assert response.status_code==200
    assert 'wordprocessingml.document' in response.headers['content-type']
    assert response.headers['cache-control']=='no-store'
    document=Document(BytesIO(response.content))
    text='\n'.join(p.text for p in document.paragraphs)
    assert 'UNSIGNED CONTRACT DRAFT' in text
    assert 'Synthetic Supplier' in text
    assert 'NOT SIGNED' in text
    assert 'LEGAL REVIEW REQUIRED' in text


def test_docx_export_rejects_invalid_payment_percentages(tmp_path):
    backend=RealBackend(runtime_dir=tmp_path/'runtime',clock=StoryClock())
    client=RoleClient(create_app(lambda:backend,dist_dir=tmp_path/'none'))
    r=client.post('/api/contracts/draft-docx',json={'data':{
        'supplier':'X','customer':'Y','scope':'Test','amount':1000,
        'milestones':[{'event':'only deposit','percentage':99}]}})
    assert r.status_code==422
