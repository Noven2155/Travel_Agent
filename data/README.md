# תיקיית הנתונים – פרויקט תיאום טיול קבוצתי

התיקייה כוללת את חבילת הנתונים של ה־POC ואת התיעוד שלה. התיעוד המלא נמצא ב־`docs/tourism_data_documentation_HE.docx` (וכטקסט ב־`docs/DATA_DESCRIPTION_HE.txt`).

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
