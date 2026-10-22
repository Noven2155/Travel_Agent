"""Rebuild demonstrator cases from catalog facts; no oracle plan is fed to a system."""
import hashlib
import json
from pathlib import Path

from travel_agent.config import INVENTORY_PATH, REPO_ROOT
from travel_agent.models import TripRequest
from travel_agent.systems import run

base = dict(city='Chicago', origin='LGA', start_date='2022-08-20', end_date='2022-08-23', travelers=4,
            budget_usd=3000, wants_car=True, pace='normal', interests=['culture', 'food'], as_of='2022-08-01')
specs = [
 ('S01', 'חופשה שאפשר לסגור', 'בקשה סגורה', 'ארבע מטיילות, חבילה עם רכב ומסלול תרבות ואוכל.', {},
  'אנחנו ארבע מטיילות. נצא מ-LGA לשיקגו ב-20 באוגוסט 2022 ונחזור ב-23 באוגוסט. התקציב הכולל לטיסות, דירה ורכב הוא 3,000 דולר. נרצה תרבות ואוכל, בקצב רגיל.', 'feasible'),
 ('S02', 'כשהתקציב לא מספיק', 'בקשה סגורה', 'אותם תאריכים; התקציב נמוך מהחבילה הזולה ביותר.', {'budget_usd':950,'wants_car':False},
  'אנחנו ארבע מטיילות מ-LGA לשיקגו, מ-20 עד 23 באוגוסט 2022. התקציב הכולל לטיסות ולינה הוא 950 דולר ואי אפשר לחרוג ממנו. לא צריך רכב. נרצה תרבות ואוכל בקצב רגיל.', 'no_package'),
 ('S03', 'מיקום או טיסה ישירה', 'בקשה גמישה', 'יש חלופות, אבל אין חבילה שמגשימה את שתי ההעדפות יחד.',
  dict(city='New York',origin='LAX',start_date='2022-10-20',end_date='2022-10-23',budget_usd=4500,wants_car=False,
       pace='relaxed',soft_prefs=['central','nonstop'],priority_weights={'central':3,'nonstop':1},as_of='2022-10-01'),
  'אנחנו ארבע מטיילות מ-LAX לניו יורק, מ-20 עד 23 באוקטובר 2022. תקרה קשיחה של 4,500 דולר לטיסות ולינה, בלי רכב. נרצה תרבות ואוכל בקצב רגוע. דירה עד 6 ק״מ מטיימס סקוור חשובה לנו פי שלושה מטיסה ישירה. אם צריך, נסכים לעצירה כדי לשמור על המיקום.', 'compromise'),
 ('S04', 'להזיז יום בשביל הטבע', 'בקשה גמישה', 'אפשר להקדים או לאחר ביום; יש פשרה בין התאריך לבין ימים יבשים.',
  dict(origin='JFK',start_date='2022-07-24',end_date='2022-07-27',budget_usd=4000,wants_car=False,pace='relaxed',
       interests=['nature','attractions'],depart_flex_days=1,return_flex_days=1,soft_prefs=['dry_days','exact_dates'],
       priority_weights={'dry_days':3,'exact_dates':1},as_of='2022-07-22'),
  'אנחנו ארבע מטיילות מ-JFK לשיקגו. מעדיפות 24 עד 27 ביולי 2022, אבל אפשר להזיז כל קצה ביום אחד ולשנות את האורך לכל היותר בלילה אחד. תקציב קשיח 4,000 דולר, בלי רכב. טבע ואטרקציות בקצב רגוע. ימים יבשים חשובים לנו פי שלושה משמירת התאריך המקורי. אפשר להחליף פעילות אם צריך.', 'compromise'),
]
cases, examples = [], {}
for id, title, kind, description, update, text, expected in specs:
 req = TripRequest.model_validate(base | update | {'request_id':id, 'free_text':text})
 result = run('rules',req)
 candidates = result.candidates
 profiles = sorted({tuple(c.get('sacrificed_prefs',[])) for c in candidates}, key=str)
 if expected == 'no_package':
  assert result.status.value == 'NO_PACKAGE_IN_CATALOG', (id,result.message)
 else:
  assert result.status.value == 'OK_PLAN', (id,result.message)
  assert candidates and candidates[0]['n_within_budget'] > 0
 if expected == 'compromise':
  assert profiles and () not in profiles, (id,profiles)
  assert len(profiles)>=2
 proof = dict(verified=True, catalog_sha256=hashlib.sha256(INVENTORY_PATH.read_bytes()).hexdigest(),
              feasible_packages=candidates[0]['n_within_budget'] if candidates else 0,
              preference_profiles=[list(p) for p in profiles],
              baseline_status=result.status.value, baseline_price=result.package.total if result.package else None,
              reason=result.message, feasibility_only=True,
              note='Catalog verification is not a prediction of agent success.')
 cases.append(dict(id=id,title=title,kind=kind,description=description,request_text=text,
                   request=req.model_dump(mode='json'),expected=expected,verification=proof))
 examples[id]=result.model_dump(mode='json')
 print(id, result.status.value, proof['feasible_packages'], proof['baseline_price'], profiles)
out=REPO_ROOT/'web'
out.mkdir(exist_ok=True)
(out/'scenarios.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
# Actual recorded Python baseline results for viewing when the backend is not connected.
(out/'recorded_baseline.json').write_text(json.dumps(examples,ensure_ascii=False))
