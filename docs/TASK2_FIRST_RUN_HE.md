<div dir="rtl" align="right">

# משימה 2 — תוצאות ההרצה הראשונה ותיקון מכסת הקריאות

**סטטוס: C השלימה הרצה אמיתית ועברה את בדיקות הקוד הקיימות. B נעצרה במכסת קריאות. משימה 2 עדיין פתוחה.**

המקור הוא קובץ ה־ZIP שהועלה מההרצה ב־Colab, `20261027T134959Z.zip`. ההרצה השתמשה ב־`main` בגרסה `155ad573d0c0bf413f461166461a94b4be16077d`. טביעות כל קובצי המקור והדאטא בדוח תאמו לעותק שנבדק, לפני התיקונים החדשים. הראיות המקוריות נשמרו ללא שינוי ב־[`evidence/task2/20261027T134959Z`](../evidence/task2/20261027T134959Z); בדיקה חוזרת מקומית ותצפיות ידניות נמצאות ב־`review.json`.

הקלט הוא S01: ארבע מטיילות לשיקגו מ־LGA, 20–23 באוגוסט 2022, תקציב 3,000 דולר, רכב, תרבות ואוכל. שתי המערכות קיבלו את אותה בקשה מבנית ואת אותו טקסט, מודל ונתונים, בהרצה נפרדת בזו אחר זו. לא נמסרה להן תשובת בייסליין מוכנה.

| נתון | B — סוכן יחיד | C — שלושה סוכנים |
|---:|---:|---:|
| תוצאה מקורית | `TECHNICAL_ERROR` | `OK_PLAN` |
| זמן לפי המערכת | 50.794 שניות | 74.906 שניות |
| זמן כולל התהליך והאתחול | 57.788 שניות | 80.923 שניות |
| סבבי תכנון | 1 | 1 |
| קריאות מודל שהושלמו | 17 | 6 |
| ניסיונות קריאה לפי האירועים | 23 | 8 |
| קריאות שנכשלו לפי האירועים | 6 | 2 |
| טוקני קלט / פלט מדווחים | 138,990 / 3,984 | 26,239 / 3,574 |
| תוכנית סופית | לא התקבלה | התקבלה |
| מחיר חבילה | אין חבילה סופית | 1,386.80 דולר |
| בדיקות התוכנית הקיימות | לא בוצעו על תוכנית סופית | 10 מתוך 10 עברו |
| בדיקה חוזרת של הבקשה המקורית | הבקשה נשמרה | הבקשה נשמרה; 11 מתוך 11 כולל בדיקת הקלט |

מודל: `gemini/gemini-3.1-flash-lite`; טמפרטורה 0; seed 42; מגבלת פלט 8,192 טוקנים; timeout של 60 שניות לקריאה. מגבלת המערכת הכוללת הייתה 270 שניות ועד שלושה סבבי תכנון. סביבת Colab: Python 3.13.16, CrewAI 1.15.30, Google GenAI 1.65.0, Pydantic 2.12.5.

## מה גרם לכשל B

בהודעת Gemini הופיעה שגיאת `429 RESOURCE_EXHAUSTED` עם מכסה של 15 בקשות לדקה למודל במסלול החינמי. הלוג תיעד בקשות להמתין, בחלקן מעל 50 שניות. מעטפת הסוכן ניסתה שוב אחרי שתי שניות, ולא כיבדה את פרק ההמתנה הזה; בנוסף התקיימו ניסיונות חוזרים בשכבות אחרות. בתחילת C התקבלו עוד שתי שגיאות 429, אך C הצליחה בהמשך.

זו אבחנה של ההרצה המצורפת בלבד. היא אינה מוכיחה שזו הייתה סיבת כל הכשלים ההיסטוריים. אין כאן מסקנה ש־C טובה או מהירה יותר באופן כללי.

## Focused fix and main-notebook integration

The shared native Gemini adapter now spaces requests through a SQLite bucket shared by local B/C workers. The conservative default is 12 requests per minute. This is an application setting, not a statement about every account's quota. Google enforces project/model limits, and usage from other programs or runtimes remains outside this local coordinator.

On a 429 response, the adapter reads `RetryInfo` and `Retry-After`, applies the provider's delay plus a one-second margin, and retries the same request at most twice. It retains the current messages rather than restarting the agent's task. Recognized daily or zero quotas are not retried by this policy. SDK-level automatic retries are disabled so this policy owns the request timing; the outer wrapper recognizes a handled 429. Every local wait counts toward the existing 270-second process deadline and is recorded as a `rate_wait` event. No agents or planning rounds were added.

The task-specific notebook records the shared RPM setting. The main Streamlit notebook now refreshes the entire package from the selected source, including new provider modules, and receives the same temperature, seed, output limit, HTTP timeout and RPM settings. The main Streamlit dependency file pins the same CrewAI/Google SDK/Pydantic versions tested here. The UI job runner shares its limiter across local jobs and exports the effective model settings. In GitHub mode, source refresh fails visibly if the update fails. Drive mode still runs the selected Drive source and does not update it from GitHub.

Reference: [Google's rate-limit documentation](https://ai.google.dev/gemini-api/docs/rate-limits).

## חריגות ומגבלות בתוצאה

- C עברה את בדיקות הקוד, אך בבדיקה ידנית נמצאו שלוש ארוחות באורך 90, 75 ו־90 דקות, מול הנחיה של 60 דקות. זו חריגה מתועדת שהבדיקות הקיימות אינן אוכפות. היא לא תוקנה באמצעות שינוי בדיעבד של פלט המודל. תוצאת ההרצה אינה הוכחה שכל דרישת תוכן נאכפת.
- כל תאריכי התרחיש סומנו `OUT_OF_HORIZON`; ההרצה אינה בודקת תכנון ליום גשם.
- המסלול של C מצומצם: פעילות אחת ושלוש ארוחות; ביום החזרה אין פריטים מתוכננים. ההרצה מוכיחה הפקת פלט ובדיקתו, ולא איכות מסלול מלאה.
- הנתונים היסטוריים וחלק מהזמינות והאומדנים סינתטיים. החבילה אינה כוללת את כל הוצאות הטיול.
- התיקון החדש נבדק מקומית באמצעות שעון ותגובות SDK מדומים בתוך הבדיקות בלבד. לא בוצעה כאן קריאת Gemini חדשה, ולא אומת עדיין שהתיקון פותר את B בהרצה אמיתית.

בדיקות התיקון המקומיות: **134 בדיקות עברו** בסוויטה המלאה; לאחר עדכון הודעת ההמתנה עברו שוב 11 בדיקות ממוקדות. יומני הבדיקות ב־[`evidence/task2/20261027-quota-fix`](../evidence/task2/20261027-quota-fix).

## המשך משימה 2

פתחו מחדש את [מחברת ההוכחה](https://colab.research.google.com/github/Noven2155/Travel_Agent/blob/main/notebooks/travel_task2_bc_colab.ipynb), ודאו ש־Notebook access פעיל לסוד הקיים, ובחרו **Runtime → Run all**. לא צריך להחליף מפתח או לפתוח ענף. המחברת תשבט את `main` המעודכן ותייצא ניסיון חדש של שתי המערכות עם אותן הגדרות. יש להעלות את ה־ZIP החדש לשיחה זו; אין להחליף את ראיות הניסיון הראשון.

לאחר בדיקת ההרצה החדשה נמשיך לאימות [המחברת הראשית](https://colab.research.google.com/github/Noven2155/Travel_Agent/blob/main/notebooks/travel_streamlit_colab.ipynb). גם היא עודכנה, אך אין עדיין הוכחה מהרצה אמיתית שלה. משימה 3 לא נפתחה.

</div>
