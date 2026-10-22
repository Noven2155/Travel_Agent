"""Real API + real spawned systems. A missing model is explicit, never a fake success."""
import json
import time

from fastapi.testclient import TestClient
from travel_agent.api import app


def main():
    with TestClient(app) as client:
        scenarios = client.get('/api/scenarios').json()
        report=[]
        for scenario in scenarios:
            response=client.post('/api/comparisons',json=dict(request=scenario['request'],request_text=scenario['request_text'],title=scenario['title']))
            assert response.status_code==202,response.text
            cid=response.json()['id']
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                result=client.get('/api/comparisons/'+cid).json()
                if result['status']=='complete':break
                time.sleep(.15)
            assert result['status']=='complete'
            a=result['runs']['rules']['result']
            assert a['status']==scenario['verification']['baseline_status'],a
            assert result['runs']['rules']['events']
            assert client.get(f'/api/comparisons/{cid}/export').status_code==200
            report.append(dict(id=scenario['id'],states={s:r['result']['status'] for s,r in result['runs'].items()},
                               metrics={s:r['metrics'] for s,r in result['runs'].items()}))
        print(json.dumps(report,indent=2))


if __name__=='__main__':main()
