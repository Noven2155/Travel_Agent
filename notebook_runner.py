"""CLI bridge used by the notebook: real project engines, no HTTP server or public tunnel."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time

for key in ('CREWAI_DISABLE_TELEMETRY','OTEL_SDK_DISABLED'):
    os.environ.setdefault(key,'true')
os.environ.setdefault('WEATHER_MODE','fixture')


def emit(kind,**data):
    print('TRAVEL_NOTEBOOK '+json.dumps(dict(kind=kind,**data),ensure_ascii=False),flush=True)


def main():
    from travel_agent import comparison as C
    from travel_agent.models import TripRequest
    body=json.load(sys.stdin)
    output=Path(body.pop('output_path'))
    only_rules=body.pop('only_rules',False)
    request=TripRequest.model_validate(body['request'])
    if only_rules:
        from travel_agent.systems import run
        emit('progress',systems={'rules':{'state':'running','events':0}})
        result=run('rules',request).model_dump(mode='json')
        result_data=dict(id='quick-baseline',title=body['title'],status='complete',mode='baseline_check',
                         request=request.model_dump(mode='json'),request_text=body.get('request_text',''),
                         model='not_used',input_mode='structured',runs={
                           'rules':dict(state='complete',result=result,events=[],metrics=C.metrics(result,body.get('pricing') or {}))})
    else:
        result_data=C.start(request.model_dump(mode='json'),body.get('request_text',''),body['title'],
                            body.get('mode','benchmark_isolated'),body.get('input_mode','structured'),body.get('pricing'))
        comparison_id=result_data['id']
        last=None
        while True:
            result_data=C.get(comparison_id)
            snapshot={key:dict(state=slot['state'],actor=slot.get('actor'),events=len(slot.get('events',[])),
                               stage=slot.get('stage')) for key,slot in result_data['runs'].items()}
            if snapshot!=last:
                emit('progress',systems=snapshot)
                last=snapshot
            if result_data['status']=='complete':break
            time.sleep(.35)
    # Provider error text is occasionally echoed into diagnostics. Scrub complete secrets before export.
    raw=json.dumps(result_data,ensure_ascii=False,indent=2)
    for env_name in ('GEMINI_API_KEY','OPENAI_API_KEY'):
        secret=os.environ.get(env_name,'')
        if len(secret)>7:raw=raw.replace(secret,'[REDACTED]')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(raw,encoding='utf-8')
    emit('complete',path=str(output))


if __name__=='__main__':main()
