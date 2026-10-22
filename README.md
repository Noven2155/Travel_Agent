# Travel Agent — השוואת שלוש מערכות לתכנון טיול קבוצתי

פרויקט גמר, קורס Agentic AI · BIU DS23 · צוות 8 · CrewAI 1.15.

המערכת משלבת טיסות, לינה, רכב ותוכנית יומית לטיול קצר של קבוצה (ארבע מטיילות בתרחישי ההדגמה), תוך כיבוד תקציב, תאריכים, גודל קבוצה והעדפות. היא גם מזהה מצב שבו אין חבילה מתאימה ומציעה פשרה מותרת. ההיקף הנוכחי: שיקגו וניו יורק. זו מערכת המלצה ומחקר השוואתי קטן — **אין הזמנות ואין תשלומים אמיתיים**.

## שלוש המערכות

| | מערכת | תיאור |
|---|---|---|
| A | קוד דטרמיניסטי (`rules`, `rules_strong`) | חיפוש, חישוב עלויות, דירוג לפי כללים והעדפות, פשרות במסגרת הגמישות. ללא LLM. בייסליין אמיתי, לא מוחלש. |
| B | סוכן יחיד ב־CrewAI | מתכנן אחד עם כל הכלים המשותפים. |
| C | שלושה סוכנים ב־CrewAI Flow | Trip Manager (חבילה) → Places (מקומות) → Itinerary (מסלול), עם נתב בקוד שמחזיר רק את הסוכן האחראי לכשל. |

כל המערכות משתמשות באותם נתונים, כלים, אילוצים ובדיקות סיום (`final_checks`), עד 3 סבבים ו־270 שניות לכל מערכת. B ו־C משתמשות באותו מודל ובאותן הגדרות. סטטוסים: `OK_PLAN`, `NO_PACKAGE_IN_CATALOG`, `CONFLICT_UNRESOLVED`, `NEEDS_DATA`, `INVALID_REQUEST`, `TECHNICAL_ERROR`, `TIMEOUT`.

## מבנה המאגר

```
src/travel_agent/        ליבת Python: מודלים, כלים, בדיקות, מערכות A/B/C, comparison.py, api.py, Streamlit, ניטור
  systems/               rules, rules_strong, single_agent (B), multi_agent (C)
  parsing/               פענוח בקשה בטקסט חופשי (כללים / LLM)
eval/                    ערכות הערכה v1/v2/v3, ניקוד, judge, דוחות (eval/reports)
tests/                   pytest (מודל מדומה רק בתוך הבדיקות)
frontend/                ממשק React + TypeScript בעברית (RTL)
web/                     scenarios.json + recorded_baseline.json — מקור יחיד לתרחישי ההדגמה
streamlit_app.py         כניסה לממשק Streamlit (גם streamlit/app.py ל־Community Cloud)
notebooks/               מחברות Colab (Streamlit — המסלול המומלץ; ומחברת ההשוואה הוותיקה)
scripts/                 הפעלה, בניית תרחישים, smoke, אריזה, עזרי מחברת
data/                    קטלוג העבודה, מקומות, מזג אוויר וקובצי מקור
docs/                    אפיון, מסמכי בוני הסוכנים, עיצוב, ארכיון
travel_files_manifest.json  גודל ו־SHA-256 של קובצי הדרייב שמהם סונכרן המאגר (רשומת שלמות)
```

## הפעלה

### 1. Google Colab (מומלץ)

1. פתחי את `notebooks/travel_streamlit_colab.ipynb` ב־Colab (File → Open notebook → GitHub).
2. ב־Secrets שמרי `GEMINI_API_KEY` והפעילי Notebook access. המפתח לא מודפס ולא נשמר בקוד או בתוצאות.
3. Runtime → Run all. כברירת מחדל המחברת משבטת את המאגר (`SOURCE_MODE = "github"`); `SOURCE_MODE = "drive"` טוען מתיקיית `My Drive/travel` (מבנה `project/` + `data/`).
4. בתא האחרון נפתח ממשק Streamlit: בחרי תרחיש ולחצי **הרץ השוואה**. מנוע הקוד (A) פועל גם בלי מפתח.

המחברת `notebooks/travel_comparison_colab.ipynb` היא המסלול הוותיק (ipywidgets) ונשמרה לתאימות.

### 2. Streamlit מקומי

נדרש Python 3.10–3.13 (נבדק על 3.12/3.13).

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-streamlit.txt
python -m streamlit run streamlit_app.py               # או: sh start_streamlit.sh  /  START_STREAMLIT.bat
```

### 3. React + API

```bash
python -m pip install -e ".[agents,api,dev]"
python scripts/start.py          # FastAPI על 8025 + ממשק; --dev מפעיל Vite על 5173
```

`frontend/dist` אינו נשמר במאגר. בהפעלה הראשונה `scripts/start.py` מתקין את תלויות הממשק ומריץ את שרת הפיתוח. לבנייה ידנית (Node.js 20+):

```bash
cd frontend && npm install && npm run build   # prebuild מעתיק את web/scenarios.json ו־recorded_baseline.json ל־public/
```

### מודל

העתיקי `.env.example` ל־`.env` והגדירי `LLM_MODEL` ומפתח (Gemini/OpenAI/Ollama), או הגדירי דרך הממשק. אין להכניס מפתחות לקוד או ל־Git (`.env` ו־`.streamlit/secrets.toml` ב־`.gitignore`).

### בדיקות והערכה

```bash
python -m pytest -q
python scripts/smoke_comparison.py                 # הרצת API מלאה ללא מודל
python -m eval.run_eval --help                     # הערכה; תוצאות גולמיות ב־eval/results (לא נשמרות במאגר), דוחות ב־eval/reports
```

## נתונים — מקור ומגבלות

**תיאור מלא של כל קובץ נתונים (היקף, עמודות, מקור, מה סינתטי, מי משתמש בו): [`data/README.md`](data/README.md).**

קטלוג העבודה: `data/inventory.json` — 15,254 טיסות בכיוון אחד, 3,960 נכסי לינה, 1,651 רכבים, 216 תאריכים (17.4–19.11.2022; SHA-256 `39a0c9c2…7319`). `data/flights.csv`, `stays.csv`, `cars.csv` הם יצוא מלא של הקטלוג לעיון; המערכות קוראות את `inventory.json`.

- **טיסות**: Kaggle dilwong/FlightPrices (Expedia), הצעות היסטוריות בכיוון אחד, 17.4–19.11.2022.
- **לינה**: Inside Airbnb, צילום ספטמבר 2026 (מחירים); **הזמינות ל־2022 מדומה**. בניו יורק הלינה הקצרה בטווח 12 ק״מ היא בג'רזי סיטי בלבד.
- **רכב**: Cornell Car Rental (Kaggle); מחיר יומי מהמקור, **קיבולת אומדן וזמינות מדומה**.
- **מקומות**: OpenStreetMap/Overpass + Wikivoyage — שיקגו 579, ניו יורק 616 (האוכל בניו יורק ממנהטן בלבד). **`rating`, `review_count`, `typical_visit_minutes` ורוב `price_level` סינתטיים** ואינם מוחזרים מהכלים.
- **מזג אוויר**: fixtures מקומיים של Open-Meteo (`data/weather`): 54 קבצים יומיים לתרחישי ההערכה וקובץ עונה לכל עיר.
- קובצי המקור (raw), שהקטלוג נבנה מהם ושאינם נקראים בקוד: Expedia, Airbnb (`*.csv.gz`; קובץ הזמינות מפוצל לשני חלקים מתחת ל־100MB) ו־Cornell. תיעודם: `data/README.md`, `data/docs/`.

מחיר חבילה אינו עלות מלאה של טיול (ללא עמלות ניקיון/ביטוח וכו'). זמני מעבר ומשכי ביקור עשויים להיות אומדנים.

## סטטוס ובעיות ידועות (22.10.2026)

- **B ו־C טרם הושלמו מקצה לקצה מול Gemini.** בהרצה האחרונה בסביבת Colab, B הסתיימה ב־`TECHNICAL_ERROR` ו־C ב־`TIMEOUT`; הסיבה טרם אובחנה. נוסף ניטור (`monitoring.py`, `events.py`) והוספו ניסיונות חוזרים לשגיאות ספק זמניות, אך אין להניח שהבעיה נפתרה. יתרון למולטי־אייג'נט הוא השערה לבדיקה, לא תוצאה.
- **`tests/test_checks.py::test_weather_rule_rain_day_outdoor`** דווחה במסמך ההעברה כנכשלת בהרצה ממוקדת (ציפייה לפריט `dropped` עם `reason=WEATHER`, כשהבייסליין בוחר מראש פעילות פנים). בגרסה שבמאגר הבדיקה מריצה את `rules_basic` ועוברת; בהרצה על הענף הזה כל 115 הבדיקות עברו. יש לוודא שוב בסביבת Colab.
- הממשק הישן `app/streamlit_app.py` הוסר לטובת `streamlit_app.py` החדש.

## מסמכים

- אפיון וארכיטקטורה: `docs/spec/Travel_Architecture_and_Plan_HE.md` (+ `.svg`)
- מסמכי בוני הסוכנים: `docs/agent_specs/` (Markdown + Word)
- עיצוב ומוצר: `docs/DESIGN.md`, `docs/PRODUCT.md`, הנחיות לסוכני קוד: `docs/AGENTS.md`
- הפעלת Streamlit: `docs/README_STREAMLIT_HE.md`
- ארכיון (היקף קודם, לרקע בלבד): `docs/archive/`

---

## English summary

Final project (Agentic AI course, BIU DS23 team 8). Compares three planners for a short group trip (Chicago / New York) on the same data, tools and checks: **A** deterministic rules, **B** one CrewAI agent, **C** a three-agent CrewAI Flow (Trip Manager → Places → Itinerary). No real bookings.

Run: Colab (`notebooks/travel_streamlit_colab.ipynb`, key from Colab Secrets `GEMINI_API_KEY`), local Streamlit (`streamlit run streamlit_app.py`), or React + FastAPI (`python scripts/start.py`; `frontend/dist` is not committed, `npm run build` regenerates it). Tests: `python -m pytest -q`.

Known issues: B/C have not yet completed an end-to-end run with Gemini (last Colab run: B `TECHNICAL_ERROR`, C `TIMEOUT`, root cause not yet diagnosed). Availability and car capacity in the data are synthetic/estimated. See `docs/` for the specification and agent-builder documents.
