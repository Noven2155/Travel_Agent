import json
from fastapi.testclient import TestClient
from travel_agent.api import app
from travel_agent.comparison import metrics
from travel_agent.config import REPO_ROOT

client=TestClient(app)

def test_verified_scenarios_include_real_conflicts_and_four_travelers():
    rows=client.get('/api/scenarios').json()
    assert len(rows)==4
    for row in rows:
        assert row['request']['travelers']==4
        proof=row['verification']
        assert proof['verified']
        if row['expected']=='no_package': assert proof['feasible_packages']==0
        else: assert proof['feasible_packages']>0
        if row['expected']=='compromise':
            assert [] not in proof['preference_profiles']
            assert len(proof['preference_profiles'])>=2

def test_invalid_request_does_not_start_comparison():
    r=client.post('/api/comparisons',json={'request':{'city':'Paris'}})
    assert r.status_code==422

def test_unconfigured_cost_is_unknown_not_invented():
    r=dict(status='OK_PLAN',all_checks_passed=True,wall_time_s=12,rounds_used=1,llm_calls=2,
           tokens_in=1000,tokens_out=500,tool_log=[],check_report={'checks':[]})
    assert metrics(r,{})['estimated_llm_cost_usd'] is None
    m=metrics(r,{'input_per_million':1,'output_per_million':2})
    assert m['estimated_llm_cost_usd']==.002
    assert m['valid_plan']
    r['wall_time_s']=301
    assert not metrics(r,{})['valid_plan']

def test_accessibility_must_not_be_reported_as_satisfied():
    from travel_agent.systems import run
    req=json.loads((REPO_ROOT/'web'/'scenarios.json').read_text())[0]['request']
    req['accessibility']=True
    assert run('rules',req).status.value=='NEEDS_DATA'

def test_health_never_exposes_credentials():
    r=client.get('/api/health')
    assert r.status_code==200
    assert 'api_key' not in r.text.lower()

def test_model_key_validation_does_not_modify_environment(monkeypatch):
    import os
    monkeypatch.setenv('LLM_MODEL','previous/model')
    response=client.post('/api/model',json={'provider':'openai','model':'anything'})
    assert response.status_code==422
    assert os.environ['LLM_MODEL']=='previous/model'

def test_free_text_cannot_erase_the_approved_budget():
    from travel_agent.comparison import audit_approved_input
    from travel_agent.models import TripRequest
    from travel_agent.systems import run
    source=json.loads((REPO_ROOT/'web'/'scenarios.json').read_text())[0]['request']
    result=run('rules',source)
    approved=TripRequest.model_validate(dict(source,budget_usd=950))
    audited=audit_approved_input(result,approved)
    assert audited.status.value=='CONFLICT_UNRESOLVED'
    assert not audited.all_checks_passed
    assert not audited.check_report.get('budget').passed
    assert not audited.check_report.get('approved_input').passed
    assert audited.parsed_request.budget_usd==3000
    assert audited.request.budget_usd==950
