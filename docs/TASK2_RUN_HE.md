<div dir="rtl" align="right">

# משימה 2 — הוכחת הרצה של B ו־C

**עדכון לאחר הרצת Colab הראשונה: C הצליחה מול Gemini ועברה את בדיקות הקוד הקיימות; B נעצרה בשגיאת מכסה 429. משימה 2 עדיין לא הושלמה.** [התוצאות, החריגות והתיקון](TASK2_FIRST_RUN_HE.md). התיקון כולל גם את המחברת הראשית; הוא עדיין דורש הרצה אמיתית חדשה.

הסעיפים להלן שומרים את תיעוד ההכנה הראשונית. הסטטוס העדכני והראיות מפורטים בדוח המקושר מעלה. לא עברנו למשימה 3.

## מה נמצא

- `main` שנבדק: `0ee529555dfb92c0389e0b0ff096fab42b7ba126`.
- התרחיש הקיים הוא `S01` מתוך `web/scenarios.json`: שיקגו, מוצא LGA, ארבע מטיילות, 20–23 באוגוסט 2022, 3,000 דולר, רכב, תרבות ואוכל, קצב רגיל. המערכות מקבלות את הבקשה בלבד; תוצאת הבייסליין והשדות `expected` ו־`verification` אינם נמסרים לסוכנים.
- מסלול ההרצה הקיים כולל תהליך נפרד לכל מערכת, אירועי מודל וכלים, מגבלת 270 שניות ו־`final_checks`. C כוללת שלושה סוכנים בלבד. לא נוספו GM או מבקר.
- במסמך ההעברה מתוארים B ב־`TECHNICAL_ERROR` ו־C ב־`TIMEOUT`. אין במאגר יומן Gemini מלא שמאפשר לאבחן את הסיבה ההיסטורית. הדוחות השמורים הם בעיקר הרצות של A. המפתח הקיים מתועד כמאוחסן ב־Colab Secrets; הוא אינו נגיש אוטומטית לסביבת העבודה הזו.

## What changed and why

The installed CrewAI 1.15.30 Gemini adapter left the effective output-token cap and seed unset, despite receiving the generic configuration fields. Its Google HTTP client also had no configured request timeout. An offline inspection confirmed these differences. The focused native adapter now sets `max_output_tokens`, forwards the seed into the generation configuration, and configures the SDK HTTP timeout in milliseconds. This is a verified configuration defect, not an established explanation of the historical B/C failures. Private reasoning is excluded from the exported evidence.

The dedicated runner reuses the existing process supervisor and executes only B and C, sequentially. It exports the approved input, shared settings, package versions, source/data hashes, final outputs, tool logs, model events, timing and independently repeated final checks. The systems retain the same tools and validators. A saved attempt is never overwritten. A missing key stops before agent execution. No fallback or recorded plan is presented as model output.

The task-specific notebook uses the existing UI model default, `gemini/gemini-3.1-flash-lite`, without claiming that it is available under the user's key. Shared settings are temperature 0, seed 42, an output limit of 8,192 tokens and a 60-second HTTP request timeout. The larger explicit output budget accommodates a structured multi-day response; it has not been validated in a live run. Each entire system still has 270 seconds and at most three planning rounds. Model calls and guardrail retries may exceed three. The same seed does not guarantee identical or deterministic provider output.

## איך מפעילים בצורה מאובטחת

1. פתחו את [המחברת הממוקדת ב־Colab](https://colab.research.google.com/github/Noven2155/Travel_Agent/blob/main/notebooks/travel_task2_bc_colab.ipynb).
2. בחלונית **Secrets** (סמל המפתח), ודאו שקיים הסוד `GEMINI_API_KEY`. אם אינו קיים, הזינו את המפתח בחלונית Secrets בלבד. הפעילו **Notebook access** עבור המחברת הזו. אין להדביק אותו בשיחה, בתא קוד או במאגר.
3. בחרו **Runtime → Run all**. אין צורך ב־GPU. ההתקנה עשויה לארוך כמה דקות; לאחריה B ו־C ירוצו בזו אחר זו. ההרצה משתמשת בחשבון Gemini שלכם, בכפוף למודל ולמכסה הזמינים בו.
4. בסיום הורידו את ה־ZIP והעלו אותו לשיחה זו. הקובץ נוצר גם כאשר הסוכנים נכשלים. אין להסתפק בצילום מסך של סטטוס.
5. נבדוק את הראיות, נתקן רק כשל מאומת אם יימצא, ונשמור את התוצרים המתאימים ישירות ב־`main`. המחברת אינה מבקשת הרשאות כתיבה ל־GitHub ואינה שומרת מפתחות.

## Local execution

Run from the repository root after installing `requirements-task2.txt`. Configure the key through a local, ignored `.env` file or a secure environment-variable mechanism. Do not put it on the command line. Set the same non-secret settings as the notebook, then run:

<div dir="ltr" align="left">

```bash
python scripts/prove_bc.py
```

</div>

Exit code 0 means both systems passed the proof gate. Exit code 2 means the task remains incomplete, including a missing key or failed checks. Inspect the exported JSON rather than assuming a nonzero exit means no evidence was saved.

## הראיות הנשמרות

| קובץ | תוכן |
|---:|---:|
| `request.json` | הבקשה המקורית, המבנית והטקסטואלית |
| `manifest.json` | מודל והגדרות, מגבלות, גרסת מקור, גרסאות ספריות וטביעות קבצים |
| `preflight.json` | מצב ההגדרות; אינו מוכיח שהמפתח, המודל או המכסה תקינים |
| `single/`, `multi/` | פלט מלא, לוג הכלים, אירועי ההרצה, זמני התחלה/סיום, מדדים ותוצאות בדיקה חוזרת |
| `comparison.json` | תמונת ההשוואה המלאה, כולל שגיאות ואירועים |
| `summary.json` | האם ההוכחה הושלמה, אילו בדיקות נכשלו והאם נצפו תשובות מודל |

ב־TIMEOUT ייתכן שלא יתקבל פלט סופי או לוג כלים מלא; אירועי ההתקדמות שהתקבלו לפני סיום התהליך נשמרים. מקרה כזה נכשל בשער ההוכחה. יומני האירועים אינם כוללים פרומפטים או חשיבה פנימית של המודל.

## תוצאות מקומיות בלבד

**123 בדיקות עברו** על Python 3.12 ו־CrewAI 1.15.30. בדיקות חיבור הסוכנים משתמשות במודל מדומה בתוך הבדיקות בלבד; בדיקות הגדרות Gemini אינן פונות לרשת. הבדיקה הראשונית של הסוויטה נחסמה בשל תלות Streamlit חסרה; לאחר התקנתה הסוויטה המלאה עברה. מחברת Colab נבדקה תחבירית בלבד, ולא הורצה בחשבון המשתמש.

הראיות המקומיות נמצאות ב־[`evidence/task2/20261027-preflight-final`](../evidence/task2/20261027-preflight-final). התוצאה היא `NOT_RUN`, עם `task2_complete=false`, משום ש־`GEMINI_API_KEY` חסר. טרם קיימים פלטי B/C אמיתיים, זמני הרצה מול Gemini או תוצאות תקינות של תוכניות Gemini.

נתוני הקטלוג היסטוריים; זמינות הלינה והרכב כוללת הדמיה ואומדנים. הרצה אחת של תרחיש אחד תוכיח היתכנות להרצה בלבד, ולא יתרון איכותי של B או C.

</div>
