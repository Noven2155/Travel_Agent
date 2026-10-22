"""Notebook-only presentation and subprocess adapter. Source data remains in the bundled project."""
import copy
import csv
import datetime as dt
import html
import io
import json
import os
from pathlib import Path
import subprocess
import signal
import time
import zipfile

LABELS={'rules':'A · קוד','single':'B · סוכן יחיד','multi':'C · שלושה סוכנים'}
STATUS={'OK_PLAN':'תוכנית תקינה','NO_PACKAGE_IN_CATALOG':'אין חבילה בקטלוג','TECHNICAL_ERROR':'שגיאת הרצה',
        'CONFLICT_UNRESOLVED':'נותרו אילוצים','TIMEOUT':'חריגה מזמן','NEEDS_DATA':'חסר מידע','INVALID_REQUEST':'בקשה לא תקינה'}
PREFS={'central':'לינה מרכזית','nonstop':'טיסות ישירות','exact_dates':'התאריכים המקוריים','dry_days':'ימים יבשים',
       'long_days':'זמן ביעד','under_preferred_budget':'תקציב מועדף'}
ACTORS={'trip_manager':'סוכן החבילה','places':'סוכן המקומות','itinerary':'סוכן המסלול','TripPlanner':'הסוכן המתכנן','code':'קוד משותף'}
CSS='''<style>.travel-doc{direction:rtl;text-align:right;font-family:Arial,sans-serif;color:#102b43;max-width:1120px;line-height:1.75;background:#fff;padding:20px 24px}.travel-doc h2{font-size:24px;margin:0 0 12px}.travel-doc h3{font-size:19px;margin:24px 0 9px}.travel-doc h4{font-size:15px;margin:16px 0 8px}.travel-doc p{margin:8px 0 14px}.travel-doc .muted{color:#536779;font-size:13px}.travel-doc table{width:100%;border-collapse:collapse;font-size:13px;direction:rtl}.travel-doc th,.travel-doc td{padding:11px 12px;border-bottom:1px solid #dce4ec;text-align:right;vertical-align:top}.travel-doc thead{background:#f1f5fa}.travel-doc .number{direction:ltr;text-align:right;font-variant-numeric:tabular-nums}.travel-doc .note{padding:12px 16px;background:#f4f7fc;margin:12px 0;border-radius:6px}.travel-doc .ok{color:#267058}.travel-doc .warn{color:#825513}.travel-doc details{margin:12px 0;padding:8px 0;border-bottom:1px solid #dce4ec}.travel-doc summary{cursor:pointer;font-weight:bold}.travel-doc ul{padding-right:20px}.travel-doc a{color:#2559cb}.travel-doc .pills{display:flex;gap:14px;flex-wrap:wrap}.travel-doc .pills>span{padding:8px 12px;background:#f1f5fa;border-radius:4px}.travel-doc code{font-size:12px;direction:ltr;display:inline-block}.travel-doc .scroll{overflow-x:auto}.travel-doc .log{max-height:280px;overflow:auto;font-size:12px}.travel-doc .technical{direction:ltr;text-align:left;font-size:11px;overflow-wrap:anywhere}@media(max-width:600px){.travel-doc{padding:12px}.travel-doc table{font-size:11px}.travel-doc td,.travel-doc th{padding:8px 6px}}</style>'''


def e(value):return html.escape(str(value))
def dollars(value):return '—' if value is None else f'${value:,.2f}'
def percent(value):return '—' if value is None else f'{value:.0%}'
def block(content):return CSS+'<div class="travel-doc">'+content+'</div>'


def summary_rows(comparison):
    rows=[]
    for system in LABELS:
        slot=comparison.get('runs',{}).get(system)
        if not slot:
            rows.append({'system':system,'system_name':LABELS[system],'status':'NOT_RUN','valid_plan':None})
            continue
        result=slot.get('result') or {}
        row=dict(system=system,system_name=LABELS[system],status=result.get('status','RUNNING'),**(slot.get('metrics') or {}))
        if result.get('status')=='TECHNICAL_ERROR' and not result.get('llm_calls'):
            row['status']='MODEL_NOT_READY' if ('LLM not available' in result.get('message','') or 'Ollama' in result.get('message','')) else result['status']
        rows.append(row)
    return rows


def render_result(comparison):
    title=e(comparison.get('title','תוצאות'))
    rows=summary_rows(comparison)
    content=f'<h2>{title}</h2><p class="muted">תוצאות מההרצה הזו · אותם קבצים ואותו מאמת לכל שלוש המערכות</p>'
    content+='<div class="scroll"><table><thead><tr><th>מערכת</th><th>תוצאה</th><th>תוכנית תקינה</th><th>זמן מנוע</th><th>מחיר חבילה</th><th>כיסוי עניין</th><th>כלים / מודל</th><th>עלות מודל משוערת</th></tr></thead><tbody>'
    for row in rows:
        status=row['status']
        name='לא הורץ בבדיקה המהירה' if status=='NOT_RUN' else 'נדרש חיבור מודל' if status=='MODEL_NOT_READY' else STATUS.get(status,status)
        measured=status not in ('NOT_RUN','MODEL_NOT_READY','TECHNICAL_ERROR','RUNNING')
        valid='כן' if row.get('valid_plan') else 'לא' if measured else '—'
        elapsed=f"{row['time_s']:.2f} ש׳" if measured and row.get('time_s') is not None else '—'
        calls=f"{row.get('tool_calls',0)} / {row.get('llm_calls',0)}" if status!='NOT_RUN' else '—'
        cost=dollars(row.get('estimated_llm_cost_usd')) if measured else '—'
        content+=f'<tr><td><b>{e(row["system_name"])}</b></td><td>{e(name)}</td><td>{valid}</td><td>{elapsed}</td><td class="number">{dollars(row.get("package_usd"))}</td><td>{percent(row.get("interests_coverage"))}</td><td>{calls}</td><td>{cost}</td></tr>'
    content+='</tbody></table></div><p class="muted">אפס חבילות הוא תוצאה תקינה בתרחיש בלתי אפשרי, אך אינו נחשב לתוכנית טיול מוצלחת. טוקנים ומדדים חסרים אינם תוצאה משוערת.</p>'
    for system,slot in comparison.get('runs',{}).items():
        result=slot.get('result') or {}
        metric=slot.get('metrics') or {}
        content+=f'<details><summary>{e(LABELS.get(system,system))} — החבילה, המסלול והבדיקות</summary>'
        package=result.get('package')
        if package:
            req=result.get('request') or comparison.get('request',{})
            content+=f'<p><b>מחיר לקבוצה: {dollars(package.get("total"))}</b> · {e(req.get("travelers"))} משתתפות</p>'
            for key,label in [('flight_out','הלוך'),('flight_back','חזור')]:
                f=package.get(key) or {}
                content+=f'<p><b>{label}:</b> <bdi>{e(f.get("origin"))} → {e(f.get("destination"))}</bdi> · {e(f.get("date"))} · <bdi>{e(f.get("dep","")[11:16])}–{e(f.get("arr","")[11:16])}</bdi> · {e(f.get("stops",0))} עצירות</p>'
            stay=package.get('stay') or {}
            content+=f'<p><b>לינה:</b> <bdi>{e(stay.get("title",""))}</bdi> · {e(stay.get("capacity"))} אורחים · {e(stay.get("km_to_center"))} ק״מ מהמרכז</p>'
            if stay.get('lat') is not None:
                content+=f'<p><a target="_blank" rel="noopener noreferrer" href="https://www.google.com/maps/search/?api=1&amp;query={e(stay["lat"])},{e(stay["lon"])}">מיקום הלינה במפה</a></p>'
            if package.get('car'):
                car=package['car']
                content+=f'<p><b>רכב:</b> <bdi>{e(car.get("make"))} {e(car.get("model"))}</bdi> · קיבולת משוערת: {e(car.get("estimated_capacity"))}</p>'
            soft=metric.get('soft_preferences') or {}
            if soft:
                content+='<h4>מה נשמר ועל מה מתפשרים</h4><ul>'+''.join(f'<li>{e(PREFS.get(k,k))}: {"נשמר" if v is True else "נדרשת פשרה" if v is False else "לא ידוע"}</li>'for k,v in soft.items())+'</ul>'
            for day in result.get('days',[]):
                content+=f'<h4>{e(day["date"])}</h4>'
                if not day.get('items'):content+='<p class="muted">אין פעילות מתוכננת בחלון היום הזמין.</p>'
                else:
                    content+='<table><thead><tr><th>שעה</th><th>מקום</th><th>סוג</th><th>מעבר משוער</th></tr></thead><tbody>'
                    for item in day['items']:
                        content+=f'<tr><td><bdi>{e(item["start"])}–{e(item["end"])}</bdi></td><td><bdi>{e(item.get("name",""))}</bdi></td><td>{"ארוחה" if item.get("kind")=="meal" else "פעילות"}</td><td>{e(item.get("travel_min"))} דק׳</td></tr>'
                    content+='</tbody></table>'
        else:content+=f'<p>{e(STATUS.get(result.get("status"),result.get("status","")))}</p>'
        if result.get('message'):content+=f'<p class="technical">{e(result["message"])}</p>'
        if result.get('tradeoffs'):
            content+='<h4>נימוקים ופשרות</h4><ul>'+''.join(f'<li><bdi>{e(t)}</bdi></li>'for t in result['tradeoffs'])+'</ul>'
        checks=(result.get('check_report') or {}).get('checks',[])
        if checks:content+='<h4>בדיקות</h4><ul>'+''.join(f'<li>{e(c["name"])}: {"עבר" if c["passed"] else "נכשל"} <bdi>{e("; ".join(c.get("details",[])))}</bdi></li>'for c in checks)+'</ul>'
        content+=f'<p class="muted">סבבים: {metric.get("rounds","—")} · טוקני קלט: {metric.get("tokens_in","—")} · פלט: {metric.get("tokens_out","—")}</p>'
        content+='<details><summary>לוג הכלים ומקורות המידע</summary><div class="log">'
        for item in result.get('tool_log',[]):
            content+=f'<p><code>{e(item.get("call_id"))}</code> · {e(ACTORS.get(item.get("actor"),item.get("actor")))} · {e(item.get("tool"))} · {e((item.get("output") or {}).get("source",""))}</p>'
        content+='</div></details></details>'
    content+='<div class="note">מחירי קטלוג היסטוריים וזמינות מדומה. זמני מעבר ומשך ביקור הם אומדנים. אין כאן אימות כרטיס להופעה או הזמנה בפועל. לא בוצעה הערכת ביצועי מודל אמיתי אם לא הוגדר מודל.</div>'
    return block(content)


def render_progress(systems):
    labels={'waiting':'ממתין','running':'בתהליך','complete':'הסתיים'}
    content='<h3>המערכות עובדות</h3><table><tr><th>מערכת</th><th>מצב</th><th>סוכן פעיל</th><th>אירועים</th></tr>'
    for key,slot in systems.items():
        actor=ACTORS.get(slot.get('actor'),slot.get('actor') or 'קוד משותף')
        content+=f'<tr><td>{e(LABELS.get(key,key))}</td><td>{e(labels.get(slot["state"],slot["state"]))}</td><td>{e(actor)}</td><td>{slot.get("events",0)}</td></tr>'
    return block(content+'</table><p class="muted">זהו עדכון מההרצה בפועל; אין התקדמות מתוזמנת מראש.</p>')


class NotebookSession:
    def __init__(self,project,python,credentials=None):
        self.project=Path(project)
        self.python=str(python)
        self.credentials=credentials or {}
        self.last=None
        self.results=[]
        self.exports=self.project/'runtime'/'notebook_exports'
        self.exports.mkdir(parents=True,exist_ok=True)
        self.cases=json.loads((self.project/'web'/'scenarios.json').read_text())

    def run(self,scenario_id='S01',*,request=None,request_text=None,mode='benchmark_isolated',input_mode='structured',pricing=None,only_rules=False,progress=None):
        case=next(c for c in self.cases if c['id']==scenario_id)
        request=copy.deepcopy(request or case['request'])
        stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        output=self.exports/f'{scenario_id}_{stamp}.json'
        payload=dict(request=request,request_text=request_text if request_text is not None else case['request_text'],
                     title=case['title'],mode=mode,input_mode=input_mode,pricing=pricing or {},
                     only_rules=only_rules,output_path=str(output))
        env=dict(os.environ,**self.credentials)
        # Notebook kernel and agent dependencies are isolated; child interpreters import this exact source.
        env['TRAVEL_AGENT_ROOT']=str(self.project)
        env['TRAVEL_RUNTIME_DIR']=str(self.project/'runtime')
        env['PYTHONPATH']=str(self.project/'src')
        env['CREWAI_DISABLE_TELEMETRY']='true'
        env['OTEL_SDK_DISABLED']='true'
        env['WEATHER_MODE']='fixture'
        env['PYTHONIOENCODING']='utf-8'
        env.setdefault('LLM_TIMEOUT_S','60')
        env.setdefault('LLM_MAX_TOKENS','4096')
        runner=self.project/'notebook_runner.py'
        log=self.exports/f'{scenario_id}_{stamp}.diagnostic.log'
        with log.open('w',encoding='utf-8') as err:
            proc=subprocess.Popen([self.python,str(runner)],cwd=self.project,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True,encoding='utf-8',bufsize=1,start_new_session=(os.name=='posix'))
            try:
                proc.stdin.write(json.dumps(payload,ensure_ascii=False))
                proc.stdin.close()
                for line in proc.stdout:
                    if not line.startswith('TRAVEL_NOTEBOOK '):continue
                    event=json.loads(line[len('TRAVEL_NOTEBOOK '):])
                    if event['kind']=='progress' and progress:progress(event['systems'])
                code=proc.wait(timeout=10)
                if code or not output.is_file():
                    # Do not echo provider diagnostic logs, which can include request details.
                    raise RuntimeError('ההרצה נעצרה. בדקי את שדות הבקשה ואת הגדרת המודל. קוד שגיאה: '+str(code))
            except BaseException:
                if proc.poll() is None:
                    if os.name=='posix':os.killpg(proc.pid,signal.SIGTERM)
                    else:proc.terminate()
                raise
        data=json.loads(output.read_text())
        self.last=data
        self.results.append(data)
        return data

    def export(self):
        if not self.results:raise RuntimeError('עדיין אין תוצאות לייצוא')
        stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        path=self.exports/f'travel_results_{stamp}.zip'
        flattened=[]
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            for i,result in enumerate(self.results,1):
                z.writestr(f'comparison_{i:03}.json',json.dumps(result,ensure_ascii=False,indent=2))
                for row in summary_rows(result):flattened.append(dict(comparison_id=result.get('id'),scenario=result.get('title'),**row))
            fields=sorted({key for row in flattened for key in row})
            buffer=io.StringIO(newline='')
            writer=csv.DictWriter(buffer,fieldnames=fields)
            writer.writeheader();writer.writerows(flattened)
            z.writestr('metrics.csv',buffer.getvalue().encode('utf-8-sig'))
            z.writestr('README_HE.txt','תוצאות אמיתיות מההרצות במחברת. NOT_RUN / MODEL_NOT_READY אינם כישלון של מודל שנבדק.\nמחירי הקטלוג וזמינות מדומה מתועדים במקור. טוקנים מדווחים; מחיר מודל מחושב רק אם הוגדר תעריף.\n')
        return path
