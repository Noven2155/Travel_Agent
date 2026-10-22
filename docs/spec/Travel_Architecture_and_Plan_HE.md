# ארכיטקטורת Travel Comparison Studio ותוכנית עבודה עד 30.10.2026

**עודכן:** 22.10.2026 — לוח עבודה מפורט ומפרטי סוכנים  
**בסיס:** קובצי הפרויקט שבדרייב: `AGENTS.md`, `README_HE.md`, `README_STREAMLIT_HE.md`, `src/travel_agent/*`, `scripts/*`, `tests/*`, `web/scenarios.json`, `web/recorded_baseline.json` והמחברות.  
**מצב אימות:** המסמך מבוסס על קוד ותיעוד שנקראו בדרייב. לא בוצעה כאן הרצת Gemini חיה או הרצה מחודשת של המחברת. פרטי מודל/מכסה ופריסת השירות דורשים אימות בסביבת ההרצה.

## 1. מטרת המערכת והיקף

Travel Comparison Studio משווה שלוש דרכים לתכנון אותה חופשה קבוצתית:

- **A — Code:** מנוע דטרמיניסטי של חיפוש, דירוג, בניית מועמדים ותיקון מוגבל.
- **B — Single Agent:** סוכן CrewAI יחיד (`TripPlanner`) שמקבל את כל כלי התכנון ומפיק תוכנית מלאה.
- **C — Expert Committee:** יעד מוצע: מנהל כללי סוכני, מומחי חבילות/מקומות/מסלול ומבקר איכותני. הקוד הנוכחי עדיין כולל שלושה סוכנים.

כל המערכות מקבלות את אותה בקשה, קוראות את אותו קטלוג וכללי בדיקה, ומחזירות אותו חוזה תוצאה. המוצר ממליץ בלבד: אין הזמנה, תשלום או נתוני זמינות חיים. זמינות לינה וקיבולת רכב מסומנות כנתונים סינתטיים/הערכה. אין להשתמש בדירוגים או ביקורות מומצאים.

## 2. רכיבי המוצר וההרצה

| רכיב | מיקום | אחריות |
|---|---|---|
| ממשק React/TypeScript בעברית | `frontend/src/` | הזנת בקשה, בחירת תרחיש, הרצת השוואה, שלוש תוצאות, מסלול/פשרות/בדיקות/יומן, מדדים והורדת JSON |
| API | `src/travel_agent/api.py` | health, קטלוג ותרחישים, פתיחת והשגת השוואה, היסטוריה, יצוא JSON, תצורת מודל בזיכרון |
| מתזמר השוואה | `src/travel_agent/comparison.py` | מריץ A/B/C בתהליכים מבודדים, מצב מקביל להצגה או מבודד למדידה, deadline של 270 שניות, SQLite לאירועים ולתוצאות |
| pipeline משותף | `src/travel_agent/pipeline.py` | קבלה ואימות בקשה, שלב רכב, מזג אוויר, בניית מועמדים, שלבים משותפים ותשתית חישוב |
| מודלים וחוזים | `models.py`, `checks.py` | סכמות Pydantic לבקשה, חבילה, מקומות, מסלול, סטטוס ותוצאות בדיקה |
| נתונים וכלים דטרמיניסטיים | `data_access.py`, `tools.py` | קריאה מקומית לקטלוג/מקומות/מזג אוויר וחישובי מחיר, מרחק וזמן |
| מנוע A | `systems/rules.py` | בחירת חבילה ומקומות, תזמון חמדני, בדיקות ותיקון ללא LLM |
| מנוע B | `systems/single_agent.py` | Flow עם סוכן אחד, עד 3 סבבים, תכנון ובדיקה משותפת |
| מנוע C (כיום) | `systems/multi_agent.py` | Flow עם 3 סוכנים, ניתוב תיקון לפי סוג כשל ועד 3 סבבים |
| מבנה C יעד | שינוי נדרש | GM סוכני, מומחים ומבקר איכותני; אינו ממומש עדיין |
| חיבור מודל | `systems/llm.py` | בחירת ספק/מודל מהסביבה, בדיקת זמינות ויצירת LLM משותף ל־B/C |
| יומנים ומדדים | `events.py`, `tool_log.py`, `monitoring.py`, `api.py` | אירועי שלבים/מודל/כלים, מדידת זמן ושימוש, תוצאות וצבירת מדדי benchmark |
| ממשק Streamlit/Colab | `streamlit_app.py`, `src/.../streamlit_view.py`, `streamlit_service.py`, `ui_worker.py`, `scripts/notebook_server.py` | נתיב הפעלה חלופי בפייתון וב־Colab. יש לוודא מהדורה פעילה מול סביבת הצוות לפני שמשווים ל־React/API. |
| הערכה | `eval/`, `scripts/` | מקרי בדיקה קפואים, ניקוד/איכות, הרצת הערכה, דוחות וסקריפט smoke ללא מודל |

### איך החלקים רצים יחד

1. המשתמש בוחר תרחיש או ממלא בקשה ומצב קלט.
2. React שולח `POST /api/comparisons` עם `ComparisonInput`: `request`, `request_text`, `title`, `mode`, `input_mode`, `pricing`.
3. ה־API מאמת שדות ומעביר למתזמר. בקלט טבעי נדרש גם `request_text`.
4. המתזמר יוצר ריצה לכל מערכת בתהליך נפרד. `demo_parallel` מיועד להצגה; `benchmark_isolated` מריץ למדידה מבוקרת. כל מערכת מקבלת אותם נתונים וכללי אימות.
5. כל מערכת מריצה intake → בדיקת/קבלת בחירת רכב → מזג אוויר → חיפוש מועמדי חבילה → החלטה ספציפית למערכת → בדיקות סופיות → בניית מסלול/רינדור; ב־C תתי־השלבים והניתוב מפורטים להלן.
6. אירועי התקדמות, שימוש במודל, קריאות כלים, סטטוס ותוצאה נרשמים. ה־UI מבצע polling, מציג השוואה, ומאפשר היסטוריה/יצוא.
7. timeout פנימי למערכת: 270 שניות; מדד ראשי משתמש בסף 300 שניות. אין להציג הצלחה על בסיס תוצאה שמורה או סינתטית כאילו הופקה מהרצה חיה.

## 3. קלט ופלט משותפים

### קלט מובנה (`TripRequest`)

בקשה כוללת: עיר יעד (`Chicago` או `New York`), שדה תעופה מוצא, תאריכי הלוך/חזור, מספר נוסעים, תקציב USD, האם נדרש רכב, קצב (`relaxed/normal/packed`), 1–4 תחומי עניין, תחומי הימנעות, העדפת לינה, תאריך `as_of`, גמישות תאריכים של עד יום, העדפות רכות ותקציב יעד, חלונות חסומים בכל יום, מגבלת הליכה, שעות התחלה/סיום, נגישות, איסור טיסות מוקדמות, משקלי עדיפות ודרישות לא ממופות.

הוולידציה מגבילה יעדים, שדות תעופה שמופיעים בקטלוג, תאריכים בטווח הקטלוג, נוסעים עד 6, חלון גמישות עד יום, אוצר מילים סגור ותחומי עניין/הימנעות לא חופפים. נגישות אינה נתמכת בדאטא: יש לסמן `NEEDS_DATA`, לא לטעון שנבדקה.

### קלט טבעי

`request_text` הוא טקסט חופשי. לפי חוזה ה־API, מצב `natural` חייב לכלול טקסט. המימוש והיקף הפענוח הטבעי המדויק צריכים להיבדק מול `systems/parsing/` ולסגור כתנאי שחרור; אין להניח שהטקסט מתורגם נכון לשדות בלי בדיקה.

### פלט

תוצאה לכל A/B/C כוללת סטטוס (`OK_PLAN`, `INVALID_REQUEST`, `NO_PACKAGE_IN_CATALOG`, `NEEDS_DATA`, `TECHNICAL_ERROR`, `CONFLICT_UNRESOLVED`, `TIMEOUT`), בקשה אפקטיבית, חבילה ומחיר שורות/סה״כ, פשרות/הסברים, מסלול יומי, מקורות וקריאות כלים, דוח בדיקות, זמן, סבבים, קריאות מודל/טוקנים כשדווחו, שגיאות ואירועי התקדמות. עלות מודל תחושב רק עם תעריפים שסופקו; אחרת תסומן כלא ידועה.

## 4. מערכות וסוכנים

### A — Code (ללא סוכן וללא קריאת מודל)

מנוע כללים ב־`systems/rules.py`. עושה חיפוש חלופות לפי אילוצים, ניקוד דטרמיניסטי, בחירת מקומות וכיסוי תחומי עניין, תזמון חמדני לפי מרחק/שעות פתיחה/מזג אוויר/עומס, והרצה של אותם validators. אין כאן קריאת מודל. הפלט הוא תוכנית ודוח בדיקות; אם אין בסיס נתונים מתאים מחזיר סטטוס חסר/אין חבילה.

### B — TripPlanner יחיד

- **תפקיד:** להחזיר חבילה אחת, פשרות ומסלול מלא שעוברים בדיקות, על סמך עובדות הכלים בלבד.
- **תהליך:** Flow משותף; שלב הסוכן מתכנן מתוך top-5 מועמדים (או מחפש ומתמחר שוב), בוחר מקומות ומתזמן; `final_checks` בודק ומנתב לתיקון. עד 3 סבבים; עד 12 איטרציות CrewAI בתוך משימה ועד 150 שניות לכל הפעלה, בכפוף לזמן שנותר.
- **כלים:** `search_flights`, `search_hotels`, `search_cars`, `calculate_price`, `search_places`, `get_place_details`, `get_travel_time`, `check_day_load`. כלים מוגבלים לנתונים המקומיים/חישובים; אין כתיבה למקורות הנתונים.
- **קלט סוכן:** בקשה מאומתת, מזג אוויר, מועמדי חבילות/תוצאות חיפוש, הקשר וכללי תכנון, משוב בדיקה מהסבב הקודם.
- **פלט:** `TripPlan` מובנה עם בחירת חבילה, מסלול יומי והפניות לכלי/מקורות; קוד מאמת אותו ומחשב סטטוס.
- **כשל נראה:** 503/429 של ספק עשוי לגרום לניסיון חוזר אחד אחרי 2 שניות; אם גם הוא נכשל, ההרצה נכשלת. retries אינם הבטחה לזמינות. יש למדוד קריאות בפועל.

### C — ועדת מומחים עם מנהל כללי סוכני (תכנון יעד)

**ההבדל מ־B:** B הוא סוכן יחיד שמבצע את כל התכנון. C מפריד מומחיות ומוסיף מנהל כללי שמפרש, מתווך ומכריע, לצד ביקורת איכותנית. זהו מבנה יעד; המימוש הנוכחי בקוד כולל שלושה סוכנים בלבד.

| רכיב | קלט ואחריות | כלים | פלט |
|---|---|---|---|
| מנהל כללי (GM), סוכן LLM | הבקשה המקורית כולל טקסט חופשי; מנסח brief והנחות, מחלק עבודה, משלב המלצות, מכריע בפשרות ומבקש תיקון | ללא חיפוש ישיר | PlanningBrief, DecisionRecord והסבר |
| מומחה חבילות | בוחר טיסות, לינה ורכב ומאזן מחיר/מיקום/נוחות | search_flights, search_hotels, search_cars, calculate_price | PackageDecision ומקורות |
| מומחה אטרקציות ומסעדות | מוצא מקומות לפי תחומי עניין, הימנעויות ואופי הטיול | search_places, get_place_details | PlaceShortlist ומקורות |
| מומחה מסלול | משבץ מקומות מול החבילה, קצב, חלונות, מרחקים ומזג אוויר | get_travel_time, check_day_load | ItineraryPlan |
| מבקר איכותני, סוכן LLM | משווה את התוכנית לבקשה המקורית ולדרישות כמו “רגוע”, “מקומי”, “לא תיירותי מדי” | ללא חיפוש עצמאי | QualitativeReview: מתאים/מתח/לא ברור, נימוק וראיות |
| ולידטור קוד | בודק תנאים אובייקטיביים ומדידים בלבד | בדיקות קוד | pass/fail/unknown |

**שפה חופשית:** שומרים את request_text המקורי לכל אורך הריצה; לא מכריחים כל העדפה ל־boolean. למשל “חופשה רגועה עם תחושה מקומית, שמתאימה להורים ולבני נוער” אינה תנאי שקוד יכול להוכיח. GM והמומחים מתייחסים אליה כהכוונה; המבקר מסביר התאמה, מתח או אי־ודאות. תנאים מפורשים כמו תקרת תקציב נבדקים בקוד. שואלים את המשתמש רק אם עמימות משנה מהותית את ההמלצה.

**Pipeline יעד ל־C:** 1) Intake שומר TripRequest ואת מלוא request_text. 2) GM מנסח PlanningBrief עם עדיפויות והנחות מסומנות. 3) מומחה החבילות בוחר חבילה ומחזיר מקורות ומיקום לינה. 4) מומחה המקומות מקבל את מיקום הלינה ומציע אטרקציות ומסעדות. 5) מומחה המסלול מקבל את החבילה ואת shortlist המקומות ובונה מסלול. 6) קוד בודק תנאים אובייקטיביים והמבקר בודק התאמה איכותנית. 7) GM מכריע ומנתב לכל היותר תיקון ממוקד אחד. 8) מוחזר חוזה התוצאה הקיים עם החלטה, הנחות, ביקורת, ראיות ותוצאות בדיקות; שינוי schema דורש גרסת API מפורשת.

**עלות וזמן:** GM פועל בתחילת התהליך ובשלב ההכרעה, ונוסף מבקר LLM. יש למדוד קריאות וזמן, להגביל איטרציות ולהשוות B/C באותו מודל, תצורה, קלט ו־deadline.

**ארכיטקטורה חזותית מלאה:** [פתיחת התרשים התפעולי (SVG)](https://drive.google.com/file/d/1p9sNt_9M9rOs2NyxN10CsY332KMPSQC6/view)

התרשים מציג מה המשתמש מפעיל, איך UI/API ומתזמר מריצים A/B/C, אילו קבצים וכלים נקראים, היכן נבדקים אילוצים, מה נשמר ב־SQLite/events ומה מוצג בתוצאה. קו מלא מסמן רכיב קיים בקוד; מסגרת מקווקוות מסמנת רכיב יעד שעדיין דורש מימוש. קובצי data עצמם לא הופיעו בתיקיית Drive שנבדקה, לכן התרשים מבדיל בין ציפיות הקוד לבין נתונים שלא נצפו בפועל.

**תרשים זרימת C (תכנון יעד):**

```mermaid
flowchart TB
  U["בקשה + request_text"] --> GM["GM סוכני: brief"]
  GM --> PK["מומחה חבילות"]
  PK --> PL["מומחה מקומות"]
  PL --> IT["מומחה מסלול"]
  IT --> V["Validators בקוד"]
  V --> RV["מבקר איכותני"]
  RV --> G2["GM סוכני: הכרעה"]
  V --> G2
  G2 --> O["RunResult / UI / SQLite"]
```

הזרימה סדרתית כי מומחה המקומות מקבל את מיקום הלינה שנבחר, ומומחה המסלול תלוי בחבילה וברשימת המקומות. כשל קשיח מועבר ל־GM ולמומחה האחראי לתיקון; החלטת GM אינה יכולה לעקוף validator. המימוש הנוכחי של C כולל trip_manager, places ו־itinerary בלבד. GM ומבקר הם רכיבי יעד.
### ולידטור קוד לעומת ביקורת סוכנית

ולידטור הוא קוד שמקבל תנאי ונתונים ומחזיר pass/fail/unknown. הוא יכול לבדוק מחיר מול תקציב או נוסעים מול קיבולת ידועה; הוא אינו יכול להוכיח שהמסלול “אותנטי” או “רגוע”. את אלה מעריך סוכן עם נימוק והפניות לראיות. יש להציג בנפרד בדיקות קשיחות וביקורת איכותנית.
## 4A. חוזי קלט/פלט ברמת שדות

**מקור הסכמה:** חוזי TripRequest, PackageDecision, PlaceShortlist, ItineraryPlan, DayPlan, Item, Dropped, CheckReport ו־RunResult נבדקו מול models.py שבפרויקט. להלן השדות כפי שמוגדרים בקוד הנוכחי; חוזי GM ו־RequirementReviewer הם הצעה ל־C ואינם קיימים עדיין. סימון `?` משמעו רשות/nullable; שדות עם ברירת מחדל אינם חייבים להישלח.

### א. בקשה משותפת — TripRequest

| שדה | טיפוס | חובה/ברירת מחדל | משמעות/מקור |
|---|---|---|---|
| request_id | string | ברירת מחדל ADHOC | מזהה הבקשה/תרחיש |
| city | enum: Chicago, New York | חובה | עיר היעד |
| origin | string, 3 תווים | חובה; נשמר uppercase | קוד שדה תעופה מוצא |
| start_date, end_date | date | חובה | תאריכי הנסיעה; end_date אחרי start_date ובטווח הקטלוג |
| travelers | integer 1–MAX_TRAVELERS (עד 6 לפי האפיון) | חובה | מספר נוסעים |
| budget_usd | integer > 0 | חובה | תקרת תקציב קשיחה |
| wants_car | boolean | חובה | האם נדרש רכב |
| pace | relaxed / normal / packed | default normal | קצב הטיול |
| interests | list[Interest], 1–4 | חובה | food, culture, attractions, nightlife, family, nature, shows, shopping, extreme/adventure |
| avoid | list[Interest] | [] | תחומים להימנע מהם; לא חופפים ל־interests |
| hotel_preference | any / central | default any | העדפת לינה |
| as_of | date | חובה | תאריך ייחוס לתחזית/נתונים |
| free_text, request_text | string? | null | טקסט עזר והטקסט המקורי; שומרים request_text ללא שינוי |
| depart_flex_days, return_flex_days | integer 0–1 | 0 | גמישות תאריך לכל כיוון |
| soft_prefs | list[SoftPref] | [] | central, nonstop, exact_dates, dry_days, long_days, under_preferred_budget |
| preferred_budget_usd | integer? >0 | null | יעד רך, חייב להיות עד budget_usd |
| daily_blocked_windows | list[BlockedWindow] | [] | חלונות אסורים בכל יום; כל פריט: start, end (HH:MM), label |
| max_walk_minutes | integer? 1–120 | null | מגבלת רגל יחידה |
| day_start, day_end | HH:MM? | null | שעות יום; ברירות מחדל בקונפיגורציה אם לא נמסרו |
| accessibility | boolean | false | צורך בנגישות; אין נתוני נגישות ולכן מחייב NEEDS_DATA |
| no_early_flight_before | HH:MM? | null | שעת המראה מוקדמת ביותר |
| priority_weights | map[string,float] | {} | משקלים רק למפתחות המותרים: central, nonstop, exact_dates, dry_days, long_days, under_preferred_budget, price |
| unparsed_requirements | list[string] | [] | דרישות שהובנו אך לא ניתן למפות; יש לשמר ולסמן |

### ב. ארטיפקטים קיימים לסוכנים

| חוזה | שדות מדויקים | שימוש |
|---|---|---|
| PackageDecision | flight_out_ref:string; flight_back_ref:string; hotel_ref:string; car_ref:string?; price_call_id:string; total_price:float; tradeoffs:list[string]=[]; relaxed_constraint:string?; rationale:string (עד 600 תווים) | פלט מומחה חבילות קיים. refs מצביעים לאפשרויות כלי, והמחיר חייב להגיע מ־calculate_price |
| PlaceChoice | place_id:string; category:string=""; indoor:string="unknown"; est_duration_min:int=60; matched_prefs:list[string]=[]; reason:string=""; source_call_id:string="" | פריט ברשימה נבחרת |
| PlaceShortlist | places:list[PlaceChoice]; uncovered_prefs:list[string]=[] | פלט מומחה מקומות קיים |
| Item | place_id:string; name:string=""; kind:activity/meal="activity"; start,end:HH:MM; mode:walk/transit/drive; travel_min:int; travel_call_id:string; from_id:string=""; weather_note:string? | פעילות/ארוחה במסלול; from_id הוא stay ref או place_id |
| DayPlan | date:string; items:list[Item]=[]; flags:list[string]=[]; window:tuple[HH:MM,HH:MM]? | יום במסלול |
| Dropped | place_id:string; reason:string | מקום שלא שובץ; סיבות לדוגמה WEATHER/NO_SLOT/DAY_LOAD/CLOSED |
| ItineraryPlan | status:OK/CANNOT_SCHEDULE="OK"; days:list[DayPlan]=[]; dropped:list[Dropped]=[]; cannot_reason:DAY_LOAD/TRAVEL_TIME/WEATHER/HOTEL_TOO_FAR?; explanation:string="" | פלט מומחה מסלול קיים |
| CheckReport | checks:list[{name:string, passed:boolean, details:list[string]=[]}]; coverage:float?; rain_days:list[string]=[] | דוח בדיקות קוד |

### ג. קלט ופלט לכל תפקיד ב־C

| סוכן | קלט שדות | פלט שדות |
|---|---|---|
| GM — הצעה, סוכן LLM | request:TripRequest; original_request_text:string; candidate_summary:any[]; stage:string (brief/final); specialist_outputs:any[] בשלב הסופי; validator_report:CheckReport?; reviewer_report:QualitativeReview? | PlanningBrief המוצע: priorities:list[{statement:string, source_text:string, confidence:low/medium/high}]; tensions:list[{items:list[string], resolution_options:list[string]}]; assumptions:list[string]; clarification_needed:boolean; question:string?; routing:list[string]. DecisionRecord המוצע: selected_package_ref:string?; selected_place_ids:list[string]; accepted_tradeoffs:list[string]; unresolved:list[string]; rationale:string; evidence_call_ids:list[string]. **חוזה חדש — לא קיים ב־models.py.** |
| מומחה חבילות | request:TripRequest; brief:PlanningBrief; candidates:list[Package] (או מועמדי כלים); weather:list[DayCondition]; previous_feedback:list[string]? | PackageDecision הקיים; כל refs ו־price_call_id חייבים להופיע ביומן הכלים, ללא ערכי מחיר מומצאים |
| מומחה אטרקציות/מסעדות | request:TripRequest; brief:PlanningBrief; city:string; place_catalog:list[PlaceSummary]; previous_feedback:list[string]? | PlaceShortlist הקיים; כל PlaceChoice.source_call_id חייב להפנות לתוצאת search_places/get_place_details. המומחה אינו משנה מקור נתונים |
| מומחה מסלול | request:TripRequest; package:PackageDecision; places:PlaceShortlist; place_details:list[object]; day_conditions:list[DayCondition]; previous_feedback:list[string]? | ItineraryPlan הקיים; travel_call_id לכל מקטע נסיעה צריך להתאים לקריאת get_travel_time |
| מבקר איכותני — הצעה, סוכן LLM | original_request_text:string; request:TripRequest; final_package:Package; itinerary:ItineraryPlan; source_call_ids:list[string]; validator_report:CheckReport | QualitativeReview המוצע: assessments:list[{preference_text:string, status:fit/tension/unknown, evidence_call_ids:list[string], rationale:string}]; missing_evidence:list[string]; suggested_revision:string?. אינו מאשר אילוצים קשיחים. **חוזה חדש — לא קיים בקוד.** |

### ד. טיפוסי אפשרויות ו־metadata של כלים

| טיפוס | שדות |
|---|---|
| FlightOption | ref, origin, destination, date, arrival_date, dep, arr, fare, stops, duration, seats, airline? |
| StayOption | ref, title, market, price_per_night, km_to_center, lat, lon, capacity, min_nights, max_nights, central |
| CarOption | ref, airport, make, model, vehicle_type, daily_rate, rental_days, estimated_capacity, capacity_basis="estimate" |
| PlaceSummary | place_id, name, category, tags, indoor=true/false/unknown, lat, lon, neighborhood, in_wikivoyage, has_wikidata, typical_visit_minutes, typical_visit_minutes_basis="estimate", source, license |
| DayCondition | date, lead_days, precip_mm?, precip_h?, apparent_max?, gust_max?, flags, source, fetched_at |
| ToolMeta | call_id, source, license, data_date |

כל תשובת כלי נרשמת ביומן עם `call_id`, שם כלי, args ו־output; כלי הנתונים הם לקריאה בלבד. לא להעביר לסוכנים או להציג שדות סינתטיים אסורים כגון rating/review_count/price_level.

### ה. תוצאה משותפת — RunResult

פלט הריצה השמור כולל: run_id, system (A/H/B/C), variant?, parser?, parse_notes, parse_llm_calls, request_id, status, message, request?, parsed_request?, package?, candidates[], days[], dropped[], tradeoffs[], weather_status, day_conditions[], check_report?, all_checks_passed, rounds_used, llm_calls, tokens_in, tokens_out, wall_time_s, tool_log_path?, tool_log[], notes[]. זהו חוזה הריצה; ארטיפקטי GM והמבקר יישמרו פנימית או יתווספו בגרסת API מפורשת, לא ישתנו בשקט.

**הערה חשובה למימוש:** שמות וסוגים בטבלאות של החוזים הקיימים נלקחו מ־models.py. חוזי GM והמבקר הם ממשק מוצע לחלוקה לצוות; יש לאשרם כ־Pydantic models לפני כתיבת הסוכנים. יש גם לאמת את טיפוסי `candidate_summary` ואת צורת ה־tool output ישירות מול `tools.py` לפני קיבוע, משום שהם דינמיים.
## 4B. אימות מול מימוש הנתונים

בדקתי את `models.py`, `data_access.py`, `config.py` ו־`tools.py` שב־`src/travel_agent/`. זה מאמת את הסכמה שהקוד **מצפה** לה ואת המיפויים של הכלים. קובצי המקור עצמם (`data/inventory.json`, `data/places/*.csv`, `data/weather/*`) אינם מופיעים ברשימת הקבצים והתיקיות הזמינים בדרייב, לכן אי אפשר לאמת את הדוגמאות/כל השורות בפועל, לבדוק חסרים או לאשר שכל שדה קיים בכל רשומה. בהתאם, להלן אימות מבני של הקוד, לא בדיקת איכות של תוכן הקטלוג.

### inventory.json — מבנה נדרש לפי Catalog

| נתיב/רשומה | מפתחות שהקוד קורא | הערות אימות |
|---|---|---|
| root | dates[], flights[], stays[], staysByAirport{}, cars[], carsByAirport{}, originAirports[], dataNotes? | dates הוא ציר הזמן לפענוח זמינות; dataNotes אופציונלי |
| flights[] | origin, destination, date, arrivalDate, departure, arrival, fare, seats; nonstop?, duration?, airline? | הקוד מוסיף ref מסוג F{index}; seats<=0 מסונן. FlightOption מחזיר ref/origin/destination/date/arrival_date/dep/arr/fare/stops/duration/seats/airline |
| stays[] | key, market, title?, price, lat, lon, capacity, availabilityPacked, minNightsPacked, maxNightsPacked | packed arrays מקודדים ביחס ל־dates; title עובר ניקוי/קיטוע. stay ref הוא key |
| cars[] | id, make?, model?, type?, dailyRate, capacityEstimate, blackouts[]? | blackouts משמשים לסינון חפיפת תאריכים; capacityEstimate הוא אומדן בלבד; car ref מקבל C לפני id |
| originAirports[] | code | נבנית רשימת שדות מוצא |
| staysByAirport / carsByAirport | מפתח airport וקבוצת stay keys / car ids | חייבים להפנות לרשומות הקיימות במערכים |

### places CSV — כותרות שהקוד קורא

נדרשים לפחות: `place_id`, `name`, `category`, `tags`, `indoor`, `lat`, `lon`, `typical_visit_minutes`, `source`, `license`. `tags` הוא מחרוזת עם מפריד `;`. שדות נוספים שהקוד יכול לקרוא: `subcategory`, `neighborhood`, `in_wikivoyage`, `wikidata`, `opening_hours`, `website`, `address`, `description_short`, `source_url`, `retrieved_at`. תוצאת כלי המקום מנרמלת indoor לערכי true/false/unknown, מתייחסת למשך הביקור כאומדן, ומחזירה מקור/רישיון. שדות `rating`, `review_count`, `price_level` נאסרו במפורש ואינם נחשפים לסוכנים.

### weather JSON — מבנה שהקוד מצפה לו

Fixture יומי נקודתי: `daily` עם `precipitation_sum`, `precipitation_hours`, `apparent_temperature_max`, `wind_gusts_10m_max`, `temperature_2m_max`, וכן `source`, `license`, `retrieved_at`. Fixture עונתי: `api_response.daily` עם `time[]` וערכי סדרות יומיות לאותם מדדים, בנוסף metadata של מקור/רישיון/שליפה. `data/weather` לא נמצא ברשימת התיקיות הזמינות, לכן זהו חוזה קריאה מהקוד, לא אימות של fixtures.

### מיפויי הכלים שאומתו

- טיסות: `search_flights(origin, airports, date, min_seats, direction)`; direction הוא out/back. המחיר הוא fare לאדם; תמחור כולל מתבצע בכלי נפרד.
- לינה: `search_hotels(city, check_in, check_out, guests, central)`; מסנן קיבולת, זמינות packed, מינימום/מקסימום לילות ומרחק עד 12 ק״מ (או רדיוס central).
- רכב: `search_cars(airport, start, end, travelers)`; זמינות לפי blackouts וקיבולת מוערכת. מעל 4 נוסעים מוחזר NEEDS_DATA.
- מחיר: `calculate_price(refs, travelers, nights)` מחזיר `refs`, `travelers`, `nights`, `lines{flights,lodging,car}`, `total`, `rental_days?`, `fees_complete=false`, `currency=USD`. זה המקור היחיד לסך חבילה מאומת; אינו כולל עמלות מלאות.
- מקומות: `search_places(city,tags,indoor_only,near,limit,exclude_tags)` מחזיר `places[]`, `n`, ו־metadata; `get_place_details(place_id,city?)` מוסיף opening_hours, website, address, description_short ו־source_url או status/error.
- נסיעות: `get_travel_time(pairs,mode)` מחזיר אומדן לכל זוג ומזהי call; זמן הנסיעה הוא חישוב גיאוגרפי בקוד ולא זמן ניווט חי.
- מזג אוויר: `get_forecast` הוא שלב Flow ולא כלי לסוכן; מחזיר days[] ו־weather_status עם flags/מקור/זמן שליפה/ספי סיווג.

### פערים שיש לסגור לפני חלוקת משימות פיתוח

1. לצרף/לחשוף לצוות את תיקיית `data/` מהגרסה הפעילה, ואז לבצע בדיקת JSON/CSV בפועל: שדות חסרים, טיפוסים, מזהים לא ייחודיים, הפניות שבורות, תאריכים ו־packed lengths.
2. להגדיר האם מכניסים שדות מקומות/מזג אוויר אופציונליים לכל הרשומות או שהיעדרם נשאר unknown; הקוד ממילא מנרמל חלק מהערכים החסרים.
3. בחוזה PlaceSummary שהוגדר קודם חסר שדה `subcategory` שקיים ב־PLACE_FIELDS_PUBLIC, אך כרגע אינו מוחזר על ידי `place_summary`; אין להניח שסוכן יקבל אותו עד שינוי הכלי/מודל.
4. `PackageDecision` הוא ההחלטה הפנימית; תוצאת ה־API העשירה היא `Package` עם refs, price_lines, total, price_call_id, פרטי flight_out/flight_back/stay/car אופציונליים ו־fees_complete. יש למפות ביניהם במפורש ולא לערבב את שני החוזים.
5. בפרויקט הנוכחי מיפוי קלט טבעי הוא מערכת־ספציפי (keyword ל־A, hybrid LLM ל־B/C לפי המודלים/RunResult); יש להשוות B ו־C עם אותו TripRequest מנורמל ועם אותו request_text מקורי, ולמדוד parse_llm_calls בנפרד כחלק מ־llm_calls.
## 5. כלים וחוזה הנתונים

כל כלי מחזיר JSON-serializable עם `call_id`, `source`, `license`, `data_date` ומתעד `args` ו־`output` ביומן הכלים. ה־LLM אינו מקבל שדות סינתטיים `rating`, `review_count`, `price_level`.

| כלי | מה הוא קורא/מקבל | מה הוא מחזיר |
|---|---|---|
| `search_flights` | origin, airports, date, min_seats, direction; `inventory.json` | טיסות חד-כיווניות, fare לנוסע, עצירות, זמנים, מושבים ומקור |
| `search_hotels` | city, check-in/out, guests, central; מלאי, זמינות/מינימום לילות מקודדים | אפשרויות העומדות בקיבולת/תאריכים/מרחק ומחיר ללילה |
| `search_cars` | airport, start/end, travelers; מלאי רכב | רכב/מחיר ליום/ימי השכרה; קיבולת מוערכת, מעל 4 נוסעים חסר מידע |
| `calculate_price` | הפניות טיסות/לינה/רכב, נוסעים ולילות | שורות מחיר וסה״כ; המקור היחיד למחיר חבילה תקף |
| `get_forecast` / `get_weather` | city + תאריכים + `as_of`; קובצי מזג אוויר במטמון | תנאי יום/דגלים/סטטוס תחזית ומקור |
| `search_places` | city, tags, indoor, near, limit, exclude_tags; CSV מקומות | מזהה/שם/קטגוריה/תגיות/ indoor/מיקום/משך ביקור משוער/מקור |
| `get_place_details` | place_id | שעות פתיחה (או unknown), אתר ותיאור קצר לפי נתוני המקור |
| `get_travel_time` | זוגות נקודות ומצב הליכה/תחבורה/רכב | דקות, mode, מזהה קריאה; הערכה גיאוגרפית לפי נוסחה |
| `check_day_load` | מסלול/פריטים/חלונות יום | האם היום עומד במגבלות פעילות/שעות/נסיעה |

## 6. נתונים שנקראים ונכתבים

### קריאה

- `data/inventory.json`: טיסות היסטוריות, מקומות לינה ומכוניות. טווח תאריכים מתועד 17.04.2022–19.11.2022.
- `data/places/chicago_places.csv`, `nyc_places.csv`: נתוני OpenStreetMap/Wikivoyage; כוללים מקור/רישיון ותאריך שליפה. אם קובץ עיר חסר, מקומות עשויים להיות unavailable.
- `data/weather/*.json`: מטמון מזג אוויר, תחזית עד 7 ימים; מעבר לאופק או קובץ חסר מסומן בהתאם.
- `web/scenarios.json`: ארבעה תרחישי הדגמה, ארבע נוסעות בכל תרחיש לפי המסמכים. תוצאות baseline שמורות ב־`web/recorded_baseline.json` הן לעיון בלבד, לא הרצה חיה.
- `eval/cases/*`: מקרי הערכה קפואים לגרסאות v1/v2/v3; `eval/results/` לדוחות.
- הגדרות: משתני סביבה/`.env` ומפתח ספק; המפתח לא נשמר בקוד, בתוצאות או ב־DB. ממשק ה־API מחזיק מפתח בזיכרון בלבד.

### כתיבה/תוצרים

- SQLite דרך `comparison.py`: השוואות, סטטוסי ריצה, תוצאות ואירועי מדידה. ה־DB הוא תוצר תפעולי ואינו מקור קטלוג; יש לאשר מיקום, גיבוי ומדיניות שמירה מול גרסת הקוד העדכנית.
- `ToolLog`/events: קריאות כלי, ארגומנטים/תשובות, מזהים, שלבי ריצה, מודל, זמן ושימוש. monitoring מצהיר שאינו מייצא prompt או reasoning. יש לבדוק בפועל ש־redaction מכסה את כל שמות משתני המפתח והודעות השגיאה.
- `eval/results/`: קובצי תוצאות הערכה ודוחות שנוצרו בסקריפטים.
- ייצוא JSON מ־`GET /api/comparisons/{id}/export`; היסטוריה דרך API. לפי README, הורדות מהממשק זמניות/מקומיות עד שמירה יזומה.
- מקורות `inventory.json`, CSV ו־weather נחשבים לקריאה בלבד על ידי מנוע התכנון. אין כתיבה בחזרה לקטלוג או לספקי נסיעות.

## 7. מדדים והערכת איכות

### מדד ראשי

`feasible success`: תוכנית שעוברת את כל בדיקות הקוד בתוך 300 שניות ולכל היותר 3 סבבים. תהליך נקטע אחרי 270 שניות כדי להשאיר מרווח. timeout וכשל טכני נספרים ככשל בהרצות benchmark; היעדר מודל צריך להישמר כקטגוריית setup נפרדת, לא לערבב עם ביצועי סוכן.

### מדדי השוואה

- סטטוס ותוצאה תקינה מול validators.
- זמן מנוע, זמן כולל תהליך, deadline/timeout וסבבי תיקון.
- קריאות מודל וטוקנים, אם הספק מדווח אותם; retries ושגיאות ספק.
- מספר קריאות כלים וזמני כלים לפי `call_id`.
- כיסוי תחומי עניין; התאמה להעדפות הרכות שניתן לבדוק.
- מחיר חבילה ושורות מחיר; עלות מודל רק אם הוגדרו תעריפים מאומתים.
- סוג פשרה/דרישות שלא כוסו והאם התוצאה נשארה grounded במקורות.
- מצב `demo_parallel` לדמו ומצב `benchmark_isolated` למדידות. לצורך טענה השוואתית יש להשתמש בהרצות מבודדות, אותם inputs/model/settings, ולשמור לכל ריצה נתוני תצורה ומזהה תרחיש.

אין להסיק אחוזי הצלחה ממדגם קטן או מהרצה יחידה. בדיקות API עם fake LLM מאמתות חיווט/חוזים בלבד, ואינן ראיה לאיכות מודל אמיתי.

## 8. תמונת מצב וסיכונים פתוחים

1. התקבלה שגיאת `503 UNAVAILABLE` ב־B עם 0/0 בדיקות ו־0 קריאות מודל בתצוגה שצורפה. זו שגיאת זמינות/עומס מספק, אך מוני 0 מצביעים גם על חשד שהאירועים לא נאספו/נטענו באותה ריצה. יש לאמת את המודל שנבחר, גרסת הקוד, log events והאם retry אחד התרחש.
2. C הסתיים בעבר ב־timeout ב־270.29 שניות; ללא טלמטריה פעילה אין לדעת איזה agent/קריאה חסמו. אחרי התיקון יש לבדוק אירועים לפי agent, משך כל קריאה, סבבים, retries ו־pending tools.
3. הבחירה האחרונה שנדונה למודל הייתה Gemini Flash-Lite, אך הקוד שנקרא בתיקיית הפרויקט מגדיר ברירת מחדל מקומית `ollama/qwen2.5:7b-instruct`, ומאפשר `gemini/*` דרך משתני סביבה. לא נמצאה הוכחה שהבחירה החדשה נשמרה/פעילה במהדורת הפרויקט העדכנית. צריך להכריע מודל וספק בפועל ולוודא מזהה נתמך, API key, מכסה ותאימות CrewAI.
4. מחברת Colab הפעילה, מחברת 2, אפליקציית Streamlit ותיקיית `project` אינם אותו נתיב. יש לבחור מקור אמת אחד, לוודא איזו גרסה הצוות מפעיל, ואז לעדכן manifest/README/מחברת בהתאם. לא לערוך עותק שגוי.
5. `README_STREAMLIT_HE.md` מתעד ש־Colab/Gemini אמיתי דורשים בדיקה בחשבון. `RELEASE_MANIFEST.json` של הפרויקט החדש (כיום ב־`archive/release/`) מתעד `real_model_tested: false`.
6. הנתונים היסטוריים/חלקם סינתטיים. אין להציג אותם כמחירים/זמינות נוכחיים.

## 9. תוכנית עבודה עד 30.10.2026

בעלי התפקידים להלן הם תפקידים; יש למפות אותם לאנשים בצוות. **שערים:** לא להתחיל benchmark איכות עד שחוזה הנתונים/המודל/telemetry מוסכמים; אין לשנות scope או UI בלי החלטת מוצר.

| תאריך | בעל/ת משימה | בניית סוכנים/תוצר | תנאי סיום |
|---|---|---|---|
| 22.10 | מובילת מוצר + כל הצוות | קיבוע source of truth; חוזי TripRequest/Packages/Places/Itinerary; חלוקת בעלי סוכנים; בדיקת זמינות data folder | כל מפתח קיבל מפרט עצמאי, גרסה/branch אחידים ופערי דאטא מתועדים |
| 23.10 | מפתח/ת 1 — GM | מימוש brief + decision של GM כסוכן LLM; הגדרת PlanningBrief/DecisionRecord; סמכות מוגבלת לראיות; 2 שלבי עבודה | חוזה Pydantic, unit tests לשימור טקסט/הנחות/מקורות וללא שינוי עובדות |
| 24.10 | מפתח/ת 2 — Package | מומחה חבילות: טיסות, לינה, רכב, calculate_price; PackageDecision | כל refs ו־price_call_id מגיעים מהכלים; hard budget/capacity/date checks עוברים |
| 25.10 | מפתח/ת 3 — Places | מומחה אטרקציות ומסעדות: חיפוש, פרטים, התאמות והימנעויות; PlaceShortlist | כל בחירה עם place_id ו־source_call_id; unknown נשמר; אין שדות סינתטיים |
| 26.10 | מפתח/ת 4 — Itinerary | מומחה מסלול: תזמון, meals, travel time, חלונות, pace, weather, dropped items | כל Item תואם schema ולוג כלי; day-load ונסיעות נבדקים; כשל נשמר בפלט |
| 27.10 | QA + מפתח/ת מתחלף/ת (זוג) — Reviewer | בניית מבקר איכותני וחוזה QualitativeReview; כתיבת rubric והעברת תיקון ממוקד ל־GM | כל fit/tension נתמך בראיות; unknown כשאין מידע; אין הרשאה לדרוס validators |
| 27.10 | אינטגרטור/ית + ארבעת מפתחי הסוכנים | חיבור Flow: GM brief → חבילות ומקומות → מסלול → validators + reviewer → GM decision; שמירת חלקי תוצאה | בדיקות חוזי I/O והזרימה מקצה לקצה; B נשאר סוכן יחיד, C מציג ועדת מומחים |
| 28.10 | Backend/Observability + QA | אירועי agent/stage, זמני קריאה, tokens, retries, error/status וכתיבה ל־SQLite; smoke עם fake LLM | כיסוי אירועים מלא; 0/0 מוסבר; אין secrets בלוג |
| 29.10 | QA + מודלים | בדיקות מערכת S01–S04, B/C באותו input/model/config במצב benchmark_isolated; ריצת מודל אמת רק אחרי telemetry תקינה | דוחות עם גרסה, תרחיש ומדדים; timeout/503/setup נפרדים מאיכות |
| 30.10 | מובילת שחרור + כל הצוות | תיקוני blocker, README/manifest, דמו וחבילת handoff | הוראות הפעלה, חוזים, מגבלות ידועות וגרסה ניתנת לשחזור |

**חלוקת כתיבת הסוכנים בצוות של ארבעה:** כל מפתח/ת מממש/ת סוכן אחד (GM, חבילות, מקומות, מסלול). המבקר הוא משימה חמישית חדשה, לכן נכתב בזוג/ברוטציה עם QA אחרי שממשק המסלול והמקומות זמין. כל אחד עדיין מקבל קובץ מפרט ייעודי כדי שיוכל לקחת בעלות על מודול המבקר אם חלוקת הצוות תשתנה.

**מפרט עצמאי לכל מפתח/ת (Drive):**
- [מנהל כללי — GM (Word)](https://drive.google.com/file/d/1CgWWkpYfq0_GcIh0bjTTD86jfZDQ9-qN/view)
- [מומחה חבילות (Word)](https://drive.google.com/file/d/1AdKxywQc_HaQLKG2eSRvImSMN1mz_xGk/view)
- [מומחה אטרקציות ומסעדות (Word)](https://drive.google.com/file/d/1cd9F5ZmAK4kDPcCFmRWTwgNHMbrD42Y2/view)
- [מומחה מסלול (Word)](https://drive.google.com/file/d/1zvYIHF_cuKEzdaHbKpBGbQXDocQ49x4v/view)
- [מבקר דרישות איכותני (Word)](https://drive.google.com/file/d/1ZzMuyg12-LKf_osP8taRmxJKBUtgyaN3/view)
- [תיקיית כל מפרטי הסוכנים](https://drive.google.com/drive/folders/17_nHfPl07NazXnocGNjSE-uAmKAkMyNO)


### חלוקת אחריות מוצעת לצוות

- **Product/מובילת פרויקט:** החלטות מקור אמת, הגדרת הצלחה, scope ו־sign-off.
- **Model/Agent engineer:** מודל/ספק, B/C, prompt ו־CrewAI, timeout/retry, שימוש ומחיר.
- **Backend/data engineer:** API, pipeline, data contracts, SQLite, כלים ו־provenance.
- **Frontend engineer:** React/Streamlit בהתאם למקור האמת; סטטוסי setup/running/error ותצוגת trace.
- **QA/evaluation:** מקרי הערכה, golden scenarios שאינם מוזנים למודלים, validators, ריצות מבודדות ודו״ח.

אדם אחד יכול למלא כמה תפקידים; לכל משימה צריך בעל/ת תפקיד יחיד/ה, reviewer, קובץ/בדיקה ותנאי סיום.

## 10. הגדרת Done לשחרור

- קובץ/commit אחד הוא מקור האמת והצוות יודע לפתוח אותו.
- מודל B/C נבדק באותו ספק ובאותה הגדרה, תוצאות setup נפרדות מתוצאות איכות.
- לכל agent יש input/output schema, כלים מורשים, קריטריון הצלחה ומסלול כשל.
- קטלוגים לקריאה בלבד ומקורות/רישיונות/תאריך נראים בתוצאות; אין שדות סינתטיים אסורים.
- pipeline וכתיבות DB/ייצוא מוסברים, secrets עוברים redaction, ו־SQLite לא מכיל מפתחות או prompts פרטיים.
- בדיקות אוטומטיות + smoke בלי מודל + לפחות ריצת מודל אמיתי מתועדת (אם מפתח/מכסה זמינים).
- מדדים מוצגים עם הגדרות, מצב ריצה, גרסת קוד, מודל/תצורה וגודל מדגם; אין טענות סטטיסטיות מהרצה יחידה.

## מקורות קוד שיש לשמור מסונכרנים עם המסמך

`AGENTS.md`; `README_HE.md`; `README_STREAMLIT_HE.md`; `src/travel_agent/api.py`; `comparison.py`; `pipeline.py`; `models.py`; `data_access.py`; `tools.py`; `checks.py`; `events.py`; `tool_log.py`; `monitoring.py`; `systems/rules.py`; `systems/single_agent.py`; `systems/multi_agent.py`; `systems/crew_tools.py`; `systems/llm.py`; `web/scenarios.json`; `web/recorded_baseline.json`; `eval/`; `tests/`; `scripts/`.


### השלמות בעקבות סקירת מומחים

- **חוזי עבודה פנימיים:** PlanningBrief, PackageDecision, PlaceShortlist, ItineraryPlan, QualitativeReview ו־DecisionRecord הם חוזים פנימיים טיפוסיים. לפני מימוש יש להחליט אם ממפים אותם לחוזה התוצאה הקיים או משיקים API v2; אין להניח שהשדות קיימים ב־TripPlan הנוכחי.
- **קלט המבקר:** הבקשה המקורית, TripRequest, התוכנית הסופית, מזהי המקורות ודוח הוולידטורים. הוא מחזיר לכל העדפה רכה fit/tension/unknown עם ראיות; אינו מאשר אילוצים קשיחים ואינו ממציא עובדות.
- **סמכות GM:** המומחים חייבים להחזיר מזהי קריאות/מקורות לכל טענה. GM רשאי לבחור ולפשר בין אפשרויות מגובות בלבד; אינו ממציא מחיר, זמינות או מאפייני מקום.
- **קלטים מדויקים:** מומחה חבילות מקבל TripRequest ורשימת מועמדי חבילה; מומחה המקומות מקבל TripRequest, עיר וקטלוג; מומחה המסלול מקבל את החבילה שנבחרה, shortlist, מזג אוויר וחלונות זמן. המסלול תלוי בחבילה ובמקומות ולכן אינו מקביל להם.
- **טקסט טבעי והשוואה הוגנת:** יש להגדיר לפני המימוש מי ממפה שדות קשיחים מ־request_text ל־TripRequest, כיצד מטפלים בחסר/סתירה, ולוודא ש־B ו־C מקבלים אותו טקסט מקורי ואותו TripRequest מנורמל. ההעדפות הרכות נשארות בטקסט ואינן נחשבות לדרישות קשיחות שנוצרו אוטומטית.
- **תקלות:** יש לתעד סטטוס נפרד למודל לא זמין (503/429), כשל כלי, כשל schema/grounding, אין חבילה מתאימה ו־TIMEOUT. לשמר תוצאות חלקיות היכן שהחוזה מאפשר. להגביל זמן/טוקנים כולל, לעצור בקריאות ספק שנכשלות ולא לחרוג מ־270 שניות.

### מדדי השוואה נדרשים ל־B/C

להגדיר feasible-run rate על פני תרחישים קבועים והרצות חוזרות; לדווח בנפרד timeout, כשל ספק וכשל setup. להשוות על אותו snapshot נתונים, מודל/גרסה, prompt/config ותנאי ריצה במצב benchmark_isolated. לדווח חציון וטווח או p50/p90 לזמן כולל ולזמן לפי סוכן; קריאות וטוקנים לפי קלט/פלט, עלות לפי תעריף מתוארך כשידוע, עלות לתוכנית feasible, retries ושיעור התאוששות, תוצרים חלקיים וכיסוי telemetry צפוי/נצפה. אין להסיק אמינות מהרצה יחידה או ממוני קריאות בלבד.

איכות המסלול והעדפות רכות ייבדקו ברובריקה קבועה (רלוונטיות, גיוון, קוהרנטיות של לו״ז, תמיכה במקורות ובהירות פשרות), רצוי בהערכה אנושית סמויה עם שני מעריכים ויישוב מחלוקות. מבקר LLM אינו ground truth ואינו רשאי לאשר הצלחה קשיחה. מוני אירועים 0/0 הם חסם לדיווח benchmark עד שיוסברו.

### תוספת לתוכנית העבודה

לפני benchmark מודל אמיתי יש להוסיף משימת חוזי I/O וגרסת API, rubric למבקר, מדיניות תיווך/סתירות של GM, בדיקות קבלה שמראות את ההבדל בין B ל־C, טיפול בכשלי ספק וזמן, ועדכון UI/monitoring/manifest. שער השחרור: telemetry מלאה בריצת smoke, ולידטורים קשיחים עצמאיים, ובדיקה שהסוכן המבקר לא יכול לדרוס אותם.

## 11. עדכון מפרטי סוכנים 22.10.2026

חמשת מסמכי ה־Word המקושרים לעיל הם הגרסה העדכנית והמיועדת למסירה למפתחים. הם מרחיבים את המפרטים הקודמים ומגדירים לכל תפקיד: אחריות וגבולות, סדר הפעולות ב־pipeline, שדות קלט ופלט וטיפוסים, כלים מורשים, נתונים שנקראים או נכתבים, קבצי קוד ונקודות חיבור, כללי מקוריות ואי־ודאות, התנהגות בכשל ו־retry, גבולות ריצה, תרחישי קבלה ו־Definition of Done.

### החלטות ממשק שיש לשמור

- **רצף C:** מומחה החבילות מחזיר את הלינה שנבחרה; מומחה המקומות משתמש במיקום הלינה; מומחה המסלול מקבל את החבילה ואת רשימת המקומות. לכן שלושת השלבים סדרתיים.
- **GM:** תפקיד LLM בשני שלבים עם סכמות נפרדות — brief לפני המומחים ו־decision אחריהם. אין לו כלי חיפוש. הפלט נשאר פנימי ב־CState; אין שינוי ל־RunResult או ל־API במסגרת המימוש המוגדר.
- **מבקר איכותני:** מקבל בקשה מקורית, תוצרים סופיים, דוח validators וחבילת ראיות תחומה; מחזיר satisfied / violated / unknown, מתחים וראיות. הוא אינו משנה עובדות או תוצאת בדיקת קוד.
- **מומחים קיימים:** trip_manager, places ו־itinerary נשארים תפקידי הקוד הקיימים. מפרטי ה־Word מבהירים את חוזיהם ואת נקודות החיבור, ואינם מציגים את GM או המבקר כאילו כבר מומשו.
- **נתונים וכלים:** כלים קיימים הם קריאה/חישוב בלבד; אין כתיבת הזמנה או שינוי קטלוג. כל טענה על מחיר, זמינות, שעות, משך או מרחק חייבת מקור או סימון unknown.
- **בדיקות:** לכל מפרט יש תרחישי קבלה. תוצאות GM/מבקר אינן יכולות לעקוף validators קשיחים. יש למדוד גם כשלי provider, timeout, retries, שימוש ומקורות telemetry.

במקרה של הבדל בין קובץ מפרט קודם בפורמט Markdown לבין מסמך Word, יש להשתמש במסמך ה־Word המקושר כאן כמפרט העבודה העדכני. השינוי מעדכן את תיעוד התכנון בלבד; מימוש GM והמבקר עדיין דורש פיתוח ובדיקות לפי לוח העבודה.

## 12. טכנולוגיות הפיתוח וההרצה

הטבלה מפרידה בין טכנולוגיות שזוהו במסמכי הפרויקט לבין פרטי סביבה שעדיין צריך לאמת בקובצי התלויות ובמהדורה הפעילה. שמות קבצים ומודולים אינם מספיקים כדי לקבוע גרסה או פקודת הפעלה, ולכן אין להשלים אותם בהשערה.

| שכבה | טכנולוגיה/רכיב שזוהו | שימוש | מה עדיין צריך לקבע ולאמת |
|---|---|---|---|
| ממשק משתמש | React ו־TypeScript | ממשק השוואת A/B/C בעברית, תוצאות, מדדים והיסטוריה | גרסאות Node ו־React, מנהל חבילות, פקודת build/dev, מקור האמת מול Streamlit |
| API ושרת | Python; API בפרויקט תחת `src/travel_agent/api.py` | קבלת בקשות, הרצות, תוצאות והיסטוריה | מסגרת ה־API המדויקת, גרסת Python, שרת ASGI/WSGI ופקודת הפעלה |
| תזמור סוכנים | CrewAI ו־Flow | סוכן יחיד ב־B וזרימת סוכנים ב־C | גרסת CrewAI, תלותי agent/tool, מבנה ההפעלה והגדרות timeout בפועל |
| סכמות נתונים | Pydantic | חוזים לבקשה, חבילה, מקומות, מסלול ותוצאות בדיקה | גרסה מדויקת ומקור סכמות יחיד בין UI/API/סוכנים |
| שמירה תפעולית | SQLite | תוצאות השוואה, סטטוסים ואירועי מדידה | מיקום DB, מיגרציות, גיבוי, retention והאם כל ממשקי ההרצה כותבים לאותו DB |
| נתוני דומיין | קובצי קטלוג מקומיים וכלי קריאה/חישוב | טיסות, לינה, רכב, מקומות, מזג אוויר וחישובי מחיר/מרחק/זמן | רשימת קבצים וגרסאות data snapshot, schema, provenance, רישוי ותאריך עדכון |
| מודל שפה | ממשק בחירת מודל דרך `systems/llm.py`; תועדו `ollama/qwen2.5:7b-instruct` כברירת מחדל מקומית ו־`gemini/*` דרך משתני סביבה | הפעלת B/C | ספק ומזהה מודל מאושרים למהדורה, גרסת SDK, API key/secret configuration, מכסה ותעריפים; הבחירה אינה מאומתת כחיה |
| UI חלופי | Streamlit ו־Colab | מסלול הפעלה חלופי בפייתון/מחברת | האם נתמך או הוחלף ב־React/API, ומחברת/גרסה מדויקת להפעלה |
| בדיקות והערכה | `tests/`, `eval/`, `scripts/` | בדיקות חיווט, בדיקות כלים, smoke, תרחישי benchmark ודוחות | פקודות הרצה, סביבת CI, תרחישים מחייבים, והפרדה בין fake LLM להרצת מודל אמיתי |
| תצורה וסודות | משתני סביבה ו־`.env` לפי התיעוד | הגדרת מודל/ספק; מפתח נשמר מחוץ לקוד וב־API בזיכרון בלבד | שמות משתנים מדויקים, מקור secrets בצוות, מדיניות redaction, וידוא שאין מפתח ב־SQLite או logs |
| פריסה ותפעול | תהליכים מבודדים ב־comparison.py; deadline שתועד כ־270 שניות | הרצת A/B/C, שמירת אירועים ותוצאות | פלטפורמת deployment, פקודת start, health checks, מגבלות משאבים, logging ו־shutdown |

### פרטי סביבה שחובה להוסיף לפני handoff למפתחים

1. קובצי תלות נעולים: `pyproject.toml` או `requirements*.txt` עבור Python ו־`package.json` יחד עם lockfile עבור frontend.
2. גרסאות Python, Node, React, CrewAI, Pydantic וספריות ספק ה־LLM, כפי שנקראות בפועל מהקבצים הנעולים.
3. פקודות מדויקות ליצירת סביבה, התקנה, הפעלת backend, הפעלת frontend, בדיקות ו־smoke.
4. מפתחות ותצורה: שמות משתני הסביבה, איפה כל מפתח מוגדר לצוות, ואילו ערכים לעולם לא נכתבים ל־DB או ליומן.
5. מודל וספק מאושרים ל־B/C, כולל מזהה מדויק, fallback, timeout/retry ותעריף מתוארך לצורך חישוב עלות.
6. סביבת פריסה פעילה ומקור האמת בין React/API לבין Streamlit/Colab; לציין כתובות/שירותים רק לאחר אימות, וכן תהליך עדכון ו־rollback.

עד שהפרטים האלה יאומתו מול קובצי התלויות והפריסה הפעילה, הטבלה היא מפת טכנולוגיות חלקית ולא מדריך התקנה שניתן להריץ לפי העתקה בלבד.

## 15. סנכרון התרחישים עם המחברת וקובץ ההרצה — 22.10.2026

### החלטת ועדת התרחישים

- S01 נשאר קו בסיס ישים.
- S02 עודכן בקובץ `project/web/scenarios.json`: התקציב הועלה מ־$950 ל־$1,275. על בסיס סריקת הקטלוג המתועדת לאותה בקשה, המחיר הזול ביותר הוא $1,294.80, ולכן הפער הוא $19.80 והציפייה נשארת `no_package`. הקובץ שומר את catalog SHA ואת `reverify_before_benchmark=true`; לפני benchmark חדש יש לבצע סריקה דטרמיניסטית חוזרת.
- S03 נשאר פשרה בין לינה מרכזית לטיסה ללא עצירות. לפני שימוש בתוצאת האיכות יש לוודא שהחלופות יוצרות trade-off בפועל.
- S04 נשאר פשרה בין גמישות תאריכים לימים יבשים. מדובר בנתוני מזג אוויר היסטוריים/סינתטיים ולא בתחזית חיה.
- S05 הוגדר כמועמד בלבד: התחלה ב־10:00, חלון מנוחה 13:00–15:00 ומגבלת הליכה של 25 דקות. הוא אינו מופעל למשתמשים עד אימות שמערכות A/B/C וה־validators אוכפים את השדות ושיש נתוני שעות פתיחה/מעברים מספקים.

### ממצאי התאמה מול המחברת הפעילה

המחברת הפעילה היא `travel_streamlit_colab.ipynb` (`1h620PhrnGl-IFA5JXVNT-cqxyHyQvJAY`). תא הטעינה הראשוני מעתיק את `project/web` מ־Drive לעותק העבודה. תא ההפעלה האחרון מעתיק את קובצי המעקב, אך בגרסה שנבדקה לא העתיק מחדש את `project/web/scenarios.json`. לכן הפעלה מחדש של תא ההפעלה בלבד עלולה להשאיר את עותק התרחישים הישן בעותק העבודה.

תיקון שבוצע במחברת: תא ההפעלה האחרון מעתיק כעת את `SOURCE/project/web/scenarios.json` אל `PROJECT/web/scenarios.json` לפני אתחול Streamlit. כך טעינת התרחישים בהרצה חדשה תשתמש בקובץ המעודכן גם ללא התקנה חוזרת. המחברת נבדקה כמבנה JSON תקין, נשארה עם 8 תאים, וקוד תא ההפעלה עבר בדיקת תחביר Python. לא בוצעה כאן הרצה חיה של Colab או של Gemini.

### השוואה למבנה המערכות

עדכון S02 הוא שינוי נתונים/קלט בלבד; הוא אינו משנה את חלוקת A/B/C. S05 בוחן אילוצים שכבר מופיעים בחוזה `TripRequest`, אך קיום שדה בסכמה אינו מבטיח שכל מערכת אוכפת אותו. לכן הוא נשאר מחוץ לסט הפעיל עד בדיקה בקוד ובוולידטורים.

האפיון מבחין בין C הנוכחי, הכולל שלושה סוכנים (trip_manager, places, itinerary), לבין C היעד עם מנהל כללי ומבקר איכותני. המחברת מפעילה את המימוש הקיים של שלוש המערכות, ואינה הופכת את C למבנה היעד. לא בוצע שינוי בקוד הסוכנים במסגרת עדכון התרחישים.
