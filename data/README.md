# תיקיית הנתונים — נקודת כניסה

כל קובצי הנתונים של הפרויקט נמצאים כאן. המסמך מפרט כל קובץ: מה הוא, היקפו, מקורו, ומי משתמש בו. כל המספרים נספרו מחדש בקוד (pandas/gzip) מול הקבצים שבמאגר ב־22.10.2026.

- **סט העבודה** — הקבצים שהקוד של שלוש המערכות (A כללים, B סוכן יחיד, C מולטי־אייג'נט) קורא בפועל: `inventory.json`, `places/`, `weather/`.
- **קובצי מקור (raw)** — החבילה שממנה נבנה הקטלוג. אף קוד במאגר אינו קורא אותם; הם נשמרים לעקיבות ולעיון.
- פירוט נוסף: [`README_COMPARISON_DATA_HE.md`](README_COMPARISON_DATA_HE.md) (תקציר הנתונים שמוצג גם בממשק Streamlit), [`docs/`](docs/) (תיעוד מלא של חבילת המקור), [`places/README.md`](places/README.md), [`weather/README.md`](weather/README.md).

**מסומן כסינתטי (מדומה) בכל מקום שבו הוא מופיע:** זמינות הלינה ל־2022, זמינות הרכבים, היומנים ותרחישי הבדיקה הישנים, ובקובצי המקומות — `rating`, `review_count`, `typical_visit_minutes` ורוב `price_level`. קיבולת הרכב היא **אומדן** לפי סוג רכב.

## סט העבודה

| קובץ | מה זה | היקף | שדות עיקריים | מקור / רישיון | מי משתמש |
|---|---|---|---|---|---|
| `inventory.json` (11.3MB) | הקטלוג המאוחד | 15,254 טיסות בכיוון אחד · 3,960 נכסי לינה · 1,651 רכבים · 216 תאריכים (17.4–19.11.2022) · 16 שדות מוצא · 12 קודי יעד | `flights`, `stays`, `cars`, `dates`, `originAirports`, `destinations`, `staysByAirport`, `carsByAirport`, `dataNotes` | נגזר מקובצי המקור (ראו "איך נבנה הקטלוג"). SHA-256 `39a0c9c2…87167319` | כלי החיפוש והמחיר של A/B/C (`src/travel_agent/data_access.py`, `tools.py`), ה־API, דף הנתונים ב־Streamlit, הערכה |
| `flights.csv` (1.9MB) | יצוא טבלאי של `inventory.flights` | 15,254 שורות · 11 עמודות | `date, origin, destination, fare, seats, duration, nonstop, airline, departure, arrival` | כמו הקטלוג | לעיון והורדה (דף הנתונים ב־Streamlit). המערכות לא קוראות אותו |
| `stays.csv` (5.6MB) | יצוא של `inventory.stays` | 3,960 שורות · 19 עמודות | `key, market, title, capacity, price, minNights, lat, lon, availabilityPacked…` | כמו הקטלוג | לעיון והורדה |
| `cars.csv` (0.5MB) | יצוא של `inventory.cars` | 1,651 שורות · 15 עמודות | `id, airportCodes, make, model, type, capacityEstimate, dailyRate, blackouts…` | כמו הקטלוג | לעיון והורדה |
| `places/chicago_places.csv` | מקומות בשיקגו | 579: 220 אטרקציות, 359 אוכל ושתייה · 27 עמודות | `place_id, name, category, tags, indoor, lat, lon, opening_hours, synthetic_fields` | OpenStreetMap (ODbL 1.0) + Wikivoyage (CC BY-SA 4.0), נשלף 21.10.2026 | `search_places`, `get_place_details` (A/B/C), בדיקות איכות בהערכה |
| `places/nyc_places.csv` | מקומות בניו יורק | 616: 256 אטרקציות, 360 אוכל ושתייה (כולם במנהטן) | כמו שיקגו | כמו שיקגו | כמו שיקגו |
| `places/build_places.py` | הסקריפט שבנה את קובצי המקומות | — | — | — | לעקיבות; לא רץ בזמן ריצה |
| `weather/{city}_{date}.json` | מזג אוויר יומי לתאריכי תרחישי ההערכה | 54 קבצים: 38 לשיקגו, 16 לניו יורק | משקעים, שעות משקעים, טמפרטורה מורגשת מקסימלית, משבי רוח, טמפרטורה מקסימלית | Open-Meteo Historical Forecast API (CC BY 4.0), נשלף 21.10.2026 ע״י `scripts/fetch_weather.py` | הכלי `get_forecast` (A/B/C); תרחישי הערכה v1/v2 |
| `weather/{city}_2022_season.json` | כל העונה 17.4–19.11.2022, לכל עיר | 2 קבצים | אותם שדות | כמו למעלה | גיבוי לבקשות אד־הוק בממשק בתאריך שאין לו קובץ יומי |
| `README_COMPARISON_DATA_HE.md` | תקציר הנתונים לסט ההשוואה | — | — | — | מוצג בדף הנתונים ב־Streamlit |

שלושת קובצי ה־CSV של הקטלוג שמורים ב־UTF-8 עם BOM ובסופי שורה CRLF. רשימות ומילונים (למשל `airportCodes`, `distanceKm`, `blackouts`) שמורים בתאים כמחרוזות JSON. הקבצים נשמרים במאגר בבתים מדויקים (`.gitattributes`), כדי שה־SHA ב־`travel_files_manifest.json` ימשיך להתאים.

## קובצי מקור (raw)

| קובץ | מה זה | היקף | מקור / רישיון | סינתטי? |
|---|---|---|---|---|
| `expedia_flight_sample_20k.csv` (7.6MB) | דגימת הצעות טיסה בכיוון אחד | 20,000 שורות · 27 עמודות · טיסות 17.4–19.11.2022 (216 תאריכים), איסוף 16.4–5.10.2022 · 16 שדות תעופה | Kaggle dilwong/FlightPrices (נאסף מ־Expedia). תנאי השימוש לפי דף המקור | לא |
| `airbnb_flight_destination_markets_full_listings_2026.csv.gz` (84MB) | נכסי Airbnb מ־13 שווקים בארה״ב | 138,837 שורות · 98 עמודות (90 מהמקור + 8 שנוספו) · 81,089 מועמדים ללינה קבוצתית | Inside Airbnb, צילומים 14–28.9.2026, CC BY 4.0 | לא (מחירי 2026) |
| `airbnb_flight_destination_markets_availability_2022_synthetic_part1.csv.gz` + `_part2.csv.gz` (57MB + 58MB) | זמינות לינה לכל נכס־מועמד ולכל אחד מ־216 תאריכי הטיסה | 17,477,737 שורות (8,738,869 + 8,738,868) · 14 עמודות | לוחות Inside Airbnb, הועתקו לתאריכי 2022 | **כן** — `availability_is_synthetic=True` בכל השורות |
| `cornell_car_rental_enriched.csv` (2.1MB) | רכבים להשכרה בארה״ב | 5,851 שורות · 23 עמודות | Kaggle Cornell Car Rental Dataset (kushleshkumar). תנאי השימוש לפי דף המקור | שדות ההדגמה שנוספו; `passenger_capacity_estimate` ריק בכל השורות |
| `car_availability_demo_2022.csv` (4.1MB) | טווחי אי־זמינות לרכבים | 27,354 טווחים · 5,851 רכבים · 1.1–28.12.2022 | נוצר בפרויקט | **כן** (`availability_source=synthetic_demo`) |
| `airbnb_destination_source_manifest.csv` | השווקים, תאריכי הצילום, קישורי ההורדה והספירות | 13 שורות | תיעוד העיבוד | — |
| `expedia_airport_airbnb_market_map.csv` | התאמה בין שדות התעופה לשווקי הלינה | 16 שורות | תיעוד העיבוד | — |
| `traveler_calendars_demo_2022.json` | יומנים של חמישה מטיילים (T01–T05), 1.1–31.12.2022 | 5 | נוצר בפרויקט | **כן**. מההיקף הקודם; הקוד הנוכחי לא משתמש בו |
| `tourism_group_trip_test_cases_2022.json` | תרחישי בדיקה עם תוצאה צפויה | 10 | נוצר בפרויקט | **כן**. מההיקף הקודם; ההערכה הנוכחית משתמשת ב־`eval/cases/` |
| `docs/verification_report.json` | ספירות, בדיקות gzip ו־SHA-256 של חבילת המקור | — | תיעוד | — |

## רשומת שלמות

`../travel_files_manifest.json` (בשורש המאגר) — גודל ו־SHA-256 של כל קובץ סט העבודה וקובצי הפרויקט, כפי שהיו בדרייב ב־22.10.2026. מחברת ההשוואה בודקת מולה את קובצי `data/` בהתאמה מדויקת. קובצי ה־raw לא נכללים בה; ההתאמה שלהם נבדקת מול `docs/verification_report.json` (ראו "הקובץ המפוצל").

## איך נבנה הקטלוג (מה שאפשר לאמת)

סקריפט ההכנה (`prepare_full_airbnb_markets.py`) וקוד בניית הקטלוג **אינם במאגר**. מה שכתוב כאן נבדק מול הקבצים עצמם:

- **טיסות:** 15,254 הטיסות בקטלוג הן בדיוק שורות הדגימה שהיעד שלהן מכוסה בלינה. כלומר 20,000 פחות 4,746 שורות שיעדן ATL, CLT, DTW או PHL. נבדק בהתאמה מלאה של (תאריך, מוצא, יעד, `totalFare`) ושל `seatsRemaining`. `fare` הוא `totalFare` לנוסע. הלוך וחזור נבנים בקוד מחיבור שתי רשומות נפרדות.
- **לינה:** 360 נכסים לכל אחד מ־12 שדות היעד, כולם מסוג "דירה/בית שלמים". ב־EWR: ג'רזי סיטי 199 + ניוארק 161; ב־DFW: דאלאס 210 + פורט וורת' 150. הזמינות היומית ומגבלות הלילות נארזו מקובץ הזמינות הסינתטי (Base64: 2 ביט לכל יום — 0 לא ידוע, 1 לא זמין, 2 זמין; מינימום/מקסימום לילות כ־uint16 little-endian). **מדיניות הבחירה של 3,960 הנכסים אינה מתועדת.**
- **רכבים:** 1,651 רכבים עם תעריף חיובי, במרחק אווירי של עד 65 ק״מ משדה תעופה נתמך (המרחק המרבי בפועל: 64.8 ק״מ). רכב יכול להיות משויך ליותר משדה אחד (2,281 שיוכים בסך הכול). הקיבולת היא אומדן לפי סוג: car/truck 4, suv 5, minivan 7, van 8. `blackouts` מועתקים מ־`car_availability_demo_2022.csv`.
- **יצוא ה־CSV:** `flights.csv`, `stays.csv` ו־`cars.csv` הם יצוא מלא של הרשימות בקטלוג, באותו סדר ובאותן עמודות, ללא סינון (נבדק).

## איזה נתון משמש באיזה שלב

| שלב / כלי | נתונים |
|---|---|
| `search_flights` | `inventory.json` → `flights` (שיקגו: ORD; ניו יורק: JFK, LGA, EWR) |
| `search_hotels` | `inventory.json` → `stays` + זמינות ארוזה; עד 12 ק״מ ממרכז העיר |
| `search_cars` | `inventory.json` → `cars` + `blackouts`; ימי השכרה = לילות + 1 |
| `calculate_price` | (טיסה הלוך + חזור) × נוסעים + מחיר לילה × לילות + תעריף יומי × (לילות + 1) |
| `search_places`, `get_place_details` | `places/*.csv`; הכלים לא מחזירים `rating`, `review_count` או `price_level` |
| `get_forecast` | `weather/*.json` (RAIN ≥ 5 מ"מ או ≥ 3 שעות; HEAT ≥ 35°; WIND ≥ 60 קמ"ש; מעבר ל־7 ימים מ־`as_of` → `OUT_OF_HORIZON`) |
| דף הנתונים ב־Streamlit | `inventory.json`, `flights.csv`/`stays.csv`/`cars.csv`, `places/*.csv`, `README_COMPARISON_DATA_HE.md` |

## מגבלות ידועות

- **הממשק משווה רק שיקגו וניו יורק**, אף שהקטלוג כולל 12 יעדים.
- **ניו יורק — לינה:** כל 360 הנכסים בשוק New York City (דרך JFK/LGA) דורשים מינימום של 30 לילות ומעלה. בניוארק יש נכסים לשהייה קצרה, אבל כולם רחוקים יותר מ־12 ק״מ מטיימס סקוור. לכן הלינה הקצרה שנמצאת בפועל היא **בג'רזי סיטי בלבד** (166 נכסים לשהייה של פחות מ־30 לילות בטווח 12 ק״מ).
- **ניו יורק — מקומות:** כל מקומות האוכל במנהטן. אין אוכל מברוקלין או מצפון־מזרח מנהטן, בגלל תקלות חוזרות בשרתי Overpass. האטרקציות מכל חמשת הרובעים.
- **שיקגו — טיסות:** יעד ORD בלבד; אין MDW בקטלוג. 1,366 טיסות נכנסות מ־15 שדות מוצא לאורך 216 ימים: כ־6.3 ליום בסך הכול, אבל רק כ־0.4 ליום בממוצע לכל מסלול. 1,044 טיסות יוצאות מ־ORD לחזרה, כ־4.8 ליום.
- **תקופות שונות:** הטיסות מ־2022, מחירי הלינה מצילומי ספטמבר 2026, ומחירי הרכב אינם מתוארכים.
- **מה סינתטי:** זמינות הלינה והרכב, היומנים, תרחישי `tourism_group_trip_test_cases_2022.json`, והדירוגים ומשך הביקור במקומות. זוג נכס־תאריך שחסר בזמינות (0.21% מהצירופים) נחשב **לא ידוע**, לא תפוס.
- **מזג אוויר:** נתוני historical forecast קרובים יותר לתצפיות מאשר לתחזית אמיתית של 1–7 ימים.
- **אין נתונים חיים:** אין זמינות בזמן אמת או הזמנה בפועל. המחירים אינם כוללים מסים, ניקיון, ביטוח או עמלות שאינם בשדות המקור.
- **מקומות:** אין אימות שמקום פעל ב־2022. שעות הפתיחה חלקיות: 264 מתוך 579 בשיקגו ו־412 מתוך 616 בניו יורק. כשאין מידע על שעות הפתיחה, המקום לא נחשב פתוח.

## מקורות ורישיונות

- **טיסות:** Flight Prices של dilwong ב־Kaggle (נאסף מ־Expedia) — https://www.kaggle.com/datasets/dilwong/flightprices , https://github.com/dilwong/FlightPrices
- **לינה:** Inside Airbnb — https://insideairbnb.com/get-the-data/ — רישיון CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). חובה לציין ייחוס ל־Inside Airbnb.
- **רכבים:** Cornell Car Rental Dataset ב־Kaggle — https://www.kaggle.com/datasets/kushleshkumar/cornell-car-rental-dataset
- **מקומות:** © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright); Wikivoyage, CC BY-SA 4.0 (https://en.wikivoyage.org)
- **מזג אוויר:** Open-Meteo, CC BY 4.0 (https://open-meteo.com/en/license)
- במאגר אין עותק של תנאי השימוש של מאגרי Kaggle; יש לבדוק אותם בעמודי המקור.

## תיעוד מפורט (`docs/`)

- `tourism_data_documentation_HE.docx` / `DATA_DESCRIPTION_HE.txt` — תיעוד מלא של חבילת המקור: שדות, מיפוי לקטלוג, התאמת תאריכים, מגבלות וקישורי מקור.
- `README_HE.md` — תקציר חבילת המקור. `README_HE.txt` — רשימת קובצי התיעוד.
- `airbnb_destination_dataset_README.md` — כיסוי נתוני Inside Airbnb והייחוס (באנגלית).
- `verification_report.json` — ספירות, בדיקות gzip ו־SHA-256 של חבילת המקור.

## הקובץ המפוצל

GitHub אינו מקבל קבצים מעל 100MB. לכן קובץ הזמינות המקורי `airbnb_flight_destination_markets_availability_2022_synthetic.csv.gz` (125,036,208 בתים) פוצל לשני קובצי gzip תקינים. בכל חלק יש שורת כותרת, ויחד החלקים מכילים בדיוק 17,477,737 רשומות, בסדר המקורי.

טעינה ב־pandas:

```python
from glob import glob
import pandas as pd

parts = sorted(glob('data/airbnb_flight_destination_markets_availability_2022_synthetic_part*.csv.gz'))
availability = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
```

שחזור הקובץ המקורי בשורת הפקודה (עם כותרת אחת):

```bash
cd data
B=airbnb_flight_destination_markets_availability_2022_synthetic
{ zcat ${B}_part1.csv.gz; zcat ${B}_part2.csv.gz | tail -n +2; } | gzip > ${B}.csv.gz
```

**שימו לב:** ה־SHA-256 של קובץ הזמינות ב־`docs/verification_report.json` שייך לקובץ ה־gzip המקורי. דחיסה מחדש יוצרת בתים אחרים, ולכן הוא לא יתאים לקובץ המשוחזר. כדי לבדוק התאמה, השוו את ה־SHA-256 של התוכן הלא־דחוס (נבדק ב־22.10.2026):

- SHA-256 של ה־CSV הלא־דחוס: `bd907d466bba7399e2c80351cb85747cae8984bfa22cc19fea9af2defd78d01f`
- חלק 1: 8,738,869 רשומות; חלק 2: 8,738,868 רשומות.

```bash
{ zcat ${B}_part1.csv.gz; zcat ${B}_part2.csv.gz | tail -n +2; } | sha256sum
```

קובץ הנכסים (`..._full_listings_2026.csv.gz`) לא פוצל, וה־SHA-256 שלו תואם ל־`verification_report.json` (`79ebeed0…`).
