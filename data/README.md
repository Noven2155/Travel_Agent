# תיקיית הנתונים – פרויקט Travel Agent

התיקייה כוללת את חבילת הנתונים של ה־POC ואת התיעוד שלה, וכן את נתוני המקומות (`places/`) ומזג האוויר (`weather/`) שנוספו לצורך השוואת שלוש המערכות (כללים, סוכן יחיד, מולטי־אג'נט). התיעוד המלא נמצא ב־`docs/tourism_data_documentation_HE.docx` (וכטקסט ב־`docs/DATA_DESCRIPTION_HE.txt`).

## קובצי נתונים (`data/`)

| קובץ | תוכן |
|---|---|
| `expedia_flight_sample_20k.csv` | דגימת 20,000 רשומות טיסה (27 עמודות), 17.4.2022–19.11.2022 |
| `airbnb_flight_destination_markets_full_listings_2026.csv.gz` | 138,837 נכסי Airbnb מ־13 שווקים בארה״ב (צילומי מצב מספטמבר 2026) |
| `airbnb_flight_destination_markets_availability_2022_synthetic_part1.csv.gz`, `..._part2.csv.gz` | זמינות לינה **מדומה** – 17,477,737 רשומות, 14 עמודות, מפוצל לשני חלקים (ראו למטה) |
| `cornell_car_rental_enriched.csv` | 5,851 רכבים להשכרה (23 עמודות) |
| `car_availability_demo_2022.csv` | 27,354 טווחי אי־זמינות **מדומים** לרכבים |
| `traveler_calendars_demo_2022.json` | יומנים **מדומים** של חמישה מטיילים ל־2022 |
| `tourism_group_trip_test_cases_2022.json` | עשרה תרחישי בדיקה סינתטיים עם תוצאה צפויה |
| `inventory.json` | הקטלוג המאוחד שבו משתמשת אפליקציית ה־POC |
| `airbnb_destination_source_manifest.csv` | השווקים, תאריכי המקור, קישורים ומספרי רשומות |
| `expedia_airport_airbnb_market_map.csv` | התאמה בין שדות התעופה לשווקי Airbnb ופערי כיסוי |

שני קובצי ה־CSV האחרונים הופיעו גם בחבילת התיעוד וגם בחבילת הנתונים בתוכן זהה; נשמר עותק אחד בלבד, כאן ב־`data/`.

## נתוני מקומות (`places/`) – אטרקציות ומסעדות

| קובץ | תוכן |
|---|---|
| `places/chicago_places.csv` | 579 מקומות בשיקגו: 220 אטרקציות ו־359 מקומות אוכל (27 עמודות) |
| `places/nyc_places.csv` | 616 מקומות בניו יורק: 256 אטרקציות ו־360 מקומות אוכל (אותן 27 עמודות) |
| `places/build_places.py` | הסקריפט שבנה את שני הקבצים (OpenStreetMap דרך Overpass + Wikivoyage); `--offline` בונה מחדש מהמטמון הגולמי |
| `places/README.md` | תיעוד מלא של העמודות, המקורות והשדות הסינתטיים (באנגלית) |

- **קטגוריות:** מסעדה, בר/פאב, בית קפה, מזון מהיר, מתחם אוכל, מוזיאון, תיאטרון, פארק, אטרקציה, אתר היסטורי, גלריה, קניות, פעילות, נקודת תצפית, מרכז אמנויות, גן חיות, אקווריום, פארק שעשועים.
- **כיסוי בניו יורק:** אטרקציות מכל חמשת הרובעים. מקומות אוכל **רק ממנהטן**, ללא צפון־מזרח מנהטן (East Harlem / צפון ה־UES) וללא ברוקלין, בגלל תקלות חוזרות בשרתי Overpass. הרצה חוזרת של הסקריפט תשלים רק את האזורים החסרים.
- **מקורות ורישיונות:** OpenStreetMap – © OpenStreetMap contributors, רישיון ODbL 1.0 (https://www.openstreetmap.org/copyright); Wikivoyage – CC BY-SA 4.0 (https://en.wikivoyage.org). נשלף ב־21.10.2026 (עמודת `retrieved_at`).
- **שדות סינתטיים** (מסומנים בכל שורה בעמודה `synthetic_fields`, נוצרו עם seed 42 להדגמה בלבד): `rating`, `review_count`, `typical_visit_minutes`, ורוב ערכי `price_level` (כש־`price_source=synthetic`). **אלה אינם דירוגים אמיתיים.** הכלים לא מחזירים דירוג, מספר ביקורות או רמת מחיר, ואף אחד מהשדות האלה לא משמש לדירוג מקומות או לבדיקת העיגון; משך הביקור מוחזר רק כהערכה מסומנת.
- **אינדיקציה לפנים/חוץ (`indoor`):** נגזרת בקוד מהקטגוריה של OSM; ערך לא ידוע נחשב "בחוץ" בימי גשם.

## נתוני מזג אוויר (`weather/`)

- **מקור:** Open-Meteo Historical Forecast API (https://open-meteo.com/en/docs/historical-forecast-api) – חינמי, ללא מפתח, רישיון CC BY 4.0. נשלף פעם אחת ב־21.10.2026.
- **קבצים:** `{city}_{date}.json` – קובץ לכל תאריך שנדרש בתרחישי ההערכה (39 לשיקגו, 17 לניו יורק), עם משקעים יומיים, שעות משקעים, טמפרטורה מורגשת מקסימלית, משבי רוח וטמפרטורה מקסימלית במרכז העיר. `{city}_2022_season.json` – כל עונת הקטלוג (17.4–19.11.2022), כגיבוי לבקשות אד־הוק בממשק.
- **סיווג בקוד:** גשם (RAIN) אם ≥ 5 מ"מ או ≥ 3 שעות משקעים; חום (HEAT) אם הטמפרטורה המורגשת ≥ 35°; רוח (WIND) אם משבים ≥ 60 קמ"ש; ימים יותר מ־7 ימים אחרי `as_of` מסומנים `OUT_OF_HORIZON`.
- **הסתייגות:** נתוני historical forecast קרובים יותר לתצפיות מאשר לתחזית אמיתית של 1–7 ימים.
- פרטים נוספים ב־`weather/README.md`.

## איזה נתון משמש באיזה שלב

| שלב במערכת | נתונים |
|---|---|
| חיפוש טיסות | `expedia_flight_sample_20k.csv`, `expedia_airport_airbnb_market_map.csv` |
| חיפוש לינה | `airbnb_..._full_listings_2026.csv.gz` + קובץ הזמינות המדומה (שני החלקים) |
| השכרת רכב | `cornell_car_rental_enriched.csv`, `car_availability_demo_2022.csv` |
| בחירת מקומות ושיבוץ מסלול | `places/chicago_places.csv`, `places/nyc_places.csv` |
| התאמה למזג האוויר | `weather/*.json` |

## מגבלות ידועות

- **ניו יורק:** כל הדירות בניו יורק עצמה דורשות מינימום 30 לילות, ולכן הלינה בפועל היא בג'רזי סיטי בלבד.
- **שיקגו:** הטיסות דלילות יחסית (בערך 4 טיסות ליום לכל מסלול) ואין בקטלוג את שדה MDW.
- **ללא נתונים חיים:** Amadeus נסגר, ולכן כל הנתונים שמורים מראש. אין זמינות חיה או הזמנה בפועל.
- **נתונים סינתטיים:** היומנים, זמינות הדירות וזמינות הרכבים מדומים, וכך גם הדירוגים ומשך הביקור במקומות.

## תיעוד (`docs/`)

- `tourism_data_documentation_HE.docx` – מסמך התיעוד המלא (מקורות, שדות, התאמות תאריכים, מגבלות).
- `DATA_DESCRIPTION_HE.txt` – אותו תוכן כטקסט, כולל קישורי המקורות.
- `README_HE.txt` – תקציר חבילת התיעוד.
- `README_HE.md` – תיאור חבילת הנתונים ומגבלותיה.
- `airbnb_destination_dataset_README.md` – תיעוד נתוני Inside Airbnb והייחוס (באנגלית).
- `verification_report.json` – ספירות, בדיקות תקינות וחתימות SHA256.

## מקורות ורישיונות (לפי התיעוד)

- **טיסות:** Flight Prices של dilwong ב־Kaggle (נאסף מ־Expedia) – https://www.kaggle.com/datasets/dilwong/flightprices , https://github.com/dilwong/FlightPrices
- **לינה:** Inside Airbnb – https://insideairbnb.com/get-the-data/ , ברישיון CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). יש לציין ייחוס ל־Inside Airbnb.
- **רכבים:** Cornell Car Rental Dataset ב־Kaggle – https://www.kaggle.com/datasets/kushleshkumar/cornell-car-rental-dataset
- בחבילה אין עותק של תנאי הרישיון של מאגרי Kaggle; יש לבדוק אותם בעמודי המקור.
- היומנים, זמינות הדירות וזמינות הרכבים סינתטיים ונוצרו להדגמה בלבד. אין בנתונים זמינות חיה או הזמנה בפועל.

## הקובץ המפוצל

GitHub אינו מקבל קבצים מעל 100MB, ולכן קובץ הזמינות המקורי `airbnb_flight_destination_markets_availability_2022_synthetic.csv.gz` (כ־125MB) פוצל לשני קובצי gzip תקינים. כל חלק כולל את שורת הכותרת, והחלקים מכילים יחד בדיוק 17,477,737 רשומות, בסדר המקורי.

טעינה ב־pandas:

```python
from glob import glob
import pandas as pd

parts = sorted(glob('data/airbnb_flight_destination_markets_availability_2022_synthetic_part*.csv.gz'))
availability = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
```

שחזור הקובץ המקורי בשורת הפקודה (כותרת אחת בלבד):

```bash
cd data
B=airbnb_flight_destination_markets_availability_2022_synthetic
{ zcat ${B}_part1.csv.gz; zcat ${B}_part2.csv.gz | tail -n +2; } | gzip > ${B}.csv.gz
```

**שימו לב:** חתימת ה־SHA256 של קובץ הזמינות ב־`docs/verification_report.json` מתייחסת לקובץ המקורי שלא פוצל. הקובץ המשוחזר זהה בתוכן (אותן שורות), אבל דחיסה מחדש יוצרת קובץ gzip בבתים אחרים, ולכן ה־SHA256 שלו לא יתאים. כדי לבדוק התאמה, יש להשוות את מספר השורות או את ה־SHA256 של התוכן הלא־דחוס:

- SHA256 של ה־CSV הלא־דחוס (המקורי, וגם של החלקים לאחר חיבור עם כותרת אחת): `bd907d466bba7399e2c80351cb85747cae8984bfa22cc19fea9af2defd78d01f`
- חלק 1: 8,738,869 רשומות; חלק 2: 8,738,868 רשומות; סה״כ 17,477,737.

```bash
{ zcat ${B}_part1.csv.gz; zcat ${B}_part2.csv.gz | tail -n +2; } | sha256sum
```
