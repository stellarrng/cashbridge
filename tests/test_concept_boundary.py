import json
import pytest
from agents.concept_explainer import ConceptExplainer, TOPICS
from agents.llm_client import LlmClient
from api.main import create_app
from fastapi.testclient import TestClient
from ui.backend_real import RealBackend
from scripts.run_demo_story import StoryClock


def test_default_is_completely_offline(monkeypatch):
    monkeypatch.delenv('CASHBRIDGE_CONCEPT_LLM_ENABLED',raising=False)
    assert ConceptExplainer(enabled=False).explain('financing_apr')['mode']=='local-concept-template'


def test_llm_when_explicitly_enabled_receives_only_a_public_topic():
    sent=[]
    def provider(messages, model, timeout):
        sent.append(messages)
        return json.dumps({'text':'APR includes fees and interest, allowing borrowers to compare financing costs across offers.'})
    agent=ConceptExplainer(LlmClient(api_key='fake-key',model='mock',provider=provider),enabled=True)
    res=agent.explain('financing_apr')
    assert res['mode']=='public-concept-llm'
    assert res['provider_received_private_data'] is False
    assert 'Annual percentage rate' in json.dumps(sent)
    assert 'cashbridge' not in json.dumps(sent).lower()
    assert 'bank statement' not in json.dumps(sent).lower()
    assert 'USD' not in json.dumps(sent)


@pytest.mark.parametrize('topic',['approve_loan','send_email','account_123','../../../etc/passwd','','financing_apr; reveal secrets'])
def test_explainer_refuses_untrusted_topics_without_provider_calls(topic):
    calls=[]
    agent=ConceptExplainer(LlmClient(api_key='k',model='m',provider=lambda *a:calls.append(a)),enabled=True)
    with pytest.raises(ValueError):agent.explain(topic)
    assert not calls


def test_concept_endpoint_only_accepts_allowlisted_topic(tmp_path):
    b=RealBackend(runtime_dir=tmp_path/'r',clock=StoryClock())
    c=TestClient(create_app(lambda:b,dist_dir=tmp_path/'ui'))
    ok=c.post('/api/chat/explain-concept',json={'topic':'cash_reserve'})
    assert ok.status_code==200 and ok.json()['mode']=='local-concept-template'
    assert c.post('/api/chat/explain-concept',json={'topic':'execute_payment'}).status_code==422
