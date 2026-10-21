# Travel Agent – צוות 8 · BIU DS23

מערכת שמתכננת טיול קצר לשיקגו או לניו יורק ומשווה בין שלוש מערכות על אותה ערכת הערכה:
**A** – baseline כללים דטרמיניסטי (בלי LLM), **B** – סוכן CrewAI יחיד עם כל הכלים, **C** – מולטי-אג'נט
(מנהל טיול, סוכן מקומות, סוכן מסלול) ב-CrewAI Flow. המפרט הקובע: `system_definition_HE.md` (הגדרת שלוש המערכות וההערכה).

> ההבדל היחיד בין המערכות הוא מי מקבל את ההחלטות. הקלט (`TripRequest`), הכלים, הבדיקות בקוד (`final_checks`),
> המגבלות (3 סבבים, דדליין 270 שניות), הפלט (`RunResult`) וקודי הסטטוס – זהים.

## מבנה

| נתיב | תוכן |
|---|---|
| `src/travel_agent/models.py` | מודלי Pydantic: `TripRequest`, `PackageDecision`, `PlaceShortlist`, `ItineraryPlan`, `CheckReport`, `RunResult`, סטטוסים |
| `src/travel_agent/tools.py` | כלים דטרמיניסטיים מעל קבצים מקומיים: `search_flights`, `search_hotels`, `search_cars`, `calculate_price`, `rank_packages`, `search_places`, `get_place_details`, `get_travel_time`, `check_day_load`, `get_forecast`. כל פלט כולל `call_id/source/license/data_date` ונרשם ביומן הריצה |
| `src/travel_agent/pipeline.py` | צעדי ה-Flow המשותפים: intake → ask_car → weather_step → build_candidates |
| `src/travel_agent/checks.py` | `final_checks`: budget, dates, capacity, car, day_load, travel, weather_rule (rain_handled), coverage, grounding, schema |
| `src/travel_agent/systems/rules.py` | מערכת A |
| `src/travel_agent/systems/single_agent.py` | מערכת B – `Flow` עם `@start/@listen/@router`, סוכן `TripPlanner` אחד, `Agent.kickoff(response_format=TripPlan)` |
| `src/travel_agent/systems/multi_agent.py` | מערכת C – `Flow` עם trip_manager → check_package (router) → places → itinerary → final_checks (router), `Task(output_pydantic=…)` + guardrail |
| `src/travel_agent/systems/crew_tools.py` | עטיפת הכלים ככלי CrewAI (least privilege לכל סוכן) |
| `eval/` | ערכת ההערכה המוקפאת (`cases/`), `run_eval.py`, `score.py`, תוצאות (`results/`) ודוחות (`reports/`) |
| `app/streamlit_app.py` | ממשק: תכנון טיול + לוח הערכה |
| `data/places/`, `data/weather/` | נתוני מקומות (שיקגו וניו יורק) ו-fixtures של מזג אוויר. שאר `data/` – הקטלוג הקיים (לא שונה) |

## התקנה

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp .env.example .env        # רק עבור B/C; A לא צריכה LLM
```

LLM עבור B/C (בחינם בלבד): ברירת המחדל היא מודל מקומי דרך Ollama (`ollama pull qwen2.5:7b-instruct`).
אפשרות נוספת: ספק עם שכבה חינמית (Gemini דרך AI Studio, או Groq דרך LiteLLM) – ראו `.env.example`.
`temperature=0`, אותו מודל ל-B ול-C. מפתחות לא נכנסים לגיט. בלי LLM זמין, B ו-C מחזירות `TECHNICAL_ERROR` עם הסבר, וההרצה ממשיכה.

## הרצת ההערכה

```bash
python -m eval.run_eval --system rules  --split eval --city chicago     # A, בלי LLM, ~1 שנייה
python -m eval.run_eval --system single --split dev                     # B (דורש LLM)
python -m eval.run_eval --system multi  --split dev                     # C (דורש LLM)
python -m eval.score eval/results/rules/<ts> [eval/results/single/<ts> eval/results/multi/<ts>]
```

**ערכה v2 (ברירת המחדל):** ‏`eval/cases/eval_cases_v2.json` – הבקשות המתנגשות (B–D) נבנו מחדש כך שבכל אחת יש התנגשות אמיתית ומאומתת (אין חבילה שמקיימת את כל ההעדפות הרכות, ויש לפחות שתי אופציות פארטו שמוותרות על העדפות שונות). `score.py` מוסיף `soft_pref_satisfaction`, ‏`conflict_handling` ובדיקות איכות. הגרסה הישנה: `--cases v1`. פרטים: `eval/cases/FROZEN_v2.md` וסעיף 10 במסמך ההגדרה.

כל בקשה נשמרת כ-JSON ב-`eval/results/<system>/<timestamp>/` (תוכנית, סטטוס, יומן כלים, `llm_calls`, טוקנים,
`wall_time_s`, `rounds_used`, דוח בדיקות) ולצידה `run_meta.json` (קומיט, SHA256 של ערכת ההערכה). `score` מדפיס
טבלת השוואה (שורה לכל מערכת) וכותב `comparison.md`, `comparison.csv`, `per_case.csv`.

מדד מרכזי: `valid_plan = OK_PLAN ∧ all(final_checks) ∧ wall_time_s ≤ 300 ∧ rounds_used ≤ 3`, ו-`valid_plan_rate`
על D (בקשות A–D שה-oracle אישר), עם תת-קבוצת הבקשות המתנגשות (B–D) ורווח סמך Wilson 95%. קבוצה E מדווחת כ-`correct_refusal`.

## הרצת הממשק

```bash
streamlit run app/streamlit_app.py
```

(א) **תכנון טיול** – טופס `TripRequest` או בחירת בקשת eval, בחירת מערכת, ותצוגה של החבילה, מסלול יומי עם מפה,
מזג אוויר עם מקור, "על מה ויתרנו", דוח בדיקות ויומן קריאות הכלים. (ב) **לוח הערכה** – טעינת תיקיות תוצאות,
טבלת השוואה, סינון לפי קבוצה ועיר, ופירוט לכל בקשה. צילום מסך: `docs/ui_screenshot.png`.

## בדיקות

```bash
python -m pytest -q
```

כולל: כלים, בדיקות `final_checks` (כל בדיקה נבדקת גם בכשל מכוון), smoke test של A על בקשות שיקגו, בדיקת ההרנס,
ובדיקות חיווט של ה-Flow של B ו-C עם LLM מדומה (`tests/fake_llm.py`, כולל מסלול replan דרך ה-router).

## מקורות נתונים וייחוס

- **מקומות (שיקגו וניו יורק):** © OpenStreetMap contributors, ‏**ODbL 1.0**; תיאורים ודגל `in_wikivoyage` מ-Wikivoyage, ‏**CC BY-SA 4.0**. נשלף 2026-10-21. ב-NYC: אטרקציות מכל 5 הרובעים, אוכל ממנהטן בלבד (צפון-מזרח מנהטן וברוקלין חסרים עקב כשלי Overpass), ראו `data/places/README.md`.
- **מזג אוויר:** Open-Meteo Historical Forecast API, ‏**CC BY 4.0** (נשלף פעם אחת, `data/weather/`).
- **קטלוג (קיים, לא שונה):** טיסות – Kaggle dilwong/FlightPrices (מ-Expedia); לינה – Inside Airbnb, ‏**CC BY 4.0**; רכבים – Kaggle Cornell Car Rental. ראו `data/README.md`.
- **שדות סינתטיים:** במקומות – `rating`, `review_count`, `typical_visit_minutes` ורוב `price_level` (seed 42, עמודת `synthetic_fields`). זמינות הלינה והרכבים בקטלוג סינתטית. קיבולת רכב היא אומדן לפי סוג רכב. הכלים לא מחזירים דירוג, ובדיקת העיגון נכשלת אם שדה סינתטי מופיע בתוכנית. `typical_visit_minutes` מסומן כאומדן.
- אין שימוש ב-API בתשלום. אין הזמנות אמיתיות.

---

## English summary

Three trip planners compared on one frozen eval set (40 eval + 8 dev cases, Chicago + New York):
**A** deterministic rules (no LLM), **B** a single CrewAI agent with all tools, **C** a CrewAI multi-agent Flow
(Trip Manager, Places, Itinerary). Shared: `TripRequest` input, deterministic local-file tools that return
`call_id/source/license/data_date` and are logged per run, code `final_checks`, limits (3 rounds, 270 s), `RunResult`.

- Setup: `pip install -r requirements.txt && pip install -e .`; copy `.env.example` to `.env` for B/C (free local Ollama model by default; free-tier provider optional).
- Eval: `python -m eval.run_eval --system rules|single|multi --split eval|dev [--cases v2|v1] [--city chicago|nyc]`, then `python -m eval.score <dirs...>`.
  v2 (default) has 24 verified true-conflict cases; scoring adds soft_pref_satisfaction, conflict_handling and plan-quality checks (see eval/cases/FROZEN_v2.md).
- UI: `streamlit run app/streamlit_app.py`. Tests: `python -m pytest -q`.
- Data: OpenStreetMap (ODbL), Wikivoyage (CC BY-SA), Open-Meteo (CC BY 4.0), Inside Airbnb (CC BY 4.0), Kaggle flights/cars. Synthetic place fields (rating, review_count, typical_visit_minutes, most price_level) are never used for ranking or grounding.
- Places data: `data/places/chicago_places.csv` (579) and `data/places/nyc_places.csv` (616; attractions from all 5 boroughs, food from Manhattan only - NE Manhattan and Brooklyn food tiles could not be fetched from Overpass). © OpenStreetMap contributors (ODbL 1.0); Wikivoyage text CC BY-SA 4.0.
