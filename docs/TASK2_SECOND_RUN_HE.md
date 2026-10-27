<div dir="rtl" align="right">

# משימה 2 — הרצה שנייה ותיקון תכנון B ודיווח בסיום כפוי

**סטטוס: C הצליחה שוב מול Gemini. B לא סיימה בתוך 270 שניות. משימה 2 עדיין פתוחה.**

מקור: `20261027T141444Z.zip`, שהועלה מהרצת Colab על גרסת `c982978b11acf2af42d220b50d4a2658ca13254b`. כל טביעות קובצי המקור והדאטא תאמו לגרסה זו. הקבצים המקוריים נשמרו ללא שינוי ב־[`evidence/task2/20261027T141444Z`](../evidence/task2/20261027T141444Z); `review.json` מוסיף בדיקה חוזרת והבחנה בין תוצאות המערכת לבין פגמים במעטפת הדיווח.

הקלט נשאר S01 בשיקגו. שתי המערכות השתמשו באותו מודל `gemini/gemini-3.1-flash-lite`, טמפרטורה 0, seed 42, מגבלת פלט 8,192 טוקנים, timeout של 60 שניות לקריאה וקצב מקומי משותף של 12 קריאות לדקה. לא שונו בקשת הטיול או הנתונים, ולא נמסרה לסוכנים תוכנית בייסליין.

| נתון | B — סוכן יחיד | C — שלושה סוכנים |
|---:|---:|---:|
| תוצאה מקורית | `TIMEOUT` | `OK_PLAN` |
| זמן המערכת המדווח | 270.149 שניות במעטפת הסיום הכפוי | 106.076 שניות |
| זמן כולל התהליך והאתחול | 270.149 שניות | 114.928 שניות |
| סבבים | שלישי התחיל; שני פלטים נבדקו | 1 |
| קריאות מודל שהושלמו לפי היומן | 28 | 6 |
| ניסיונות קריאה לפי היומן | 30 | 10 |
| קריאות שנכשלו / לא הושלמו | 1 / 1 | 4 / 0 |
| שגיאות 429 | לא נצפו | לא נצפו |
| שגיאות ספק | 503 — עומס זמני | ארבע שגיאות 503; ההרצה התאוששה |
| תוכנית סופית | לא התקבלה | התקבלה; 10 מתוך 10 בדיקות עברו |
| מחיר חבילה | לא נשמר פלט סופי | 1,386.80 דולר |

ההפרש הזעיר מעל 270 שניות הוא המדידה בפועל של גבול התהליך והסיום שלו. ההרצה סומנה ככישלון ולא כהצלחה בתוך התקציב. לא הוארכה מגבלת הזמן.

## מה למדנו

1. שגיאת 429 מהניסיון הקודם לא חזרה בניסיון הזה, והיומן מראה שההמתנות בקצב הקריאות אכן הופעלו. זו ראיה לפעולת התיקון, לא הבטחה שלא יהיו בעתיד חריגות מכסה.
2. ב־B, הפלט הראשון נכשל בבדיקות `travel`, `weather_rule` ו־`grounding`. הפלט השני נכשל רק ב־`weather_rule`. סבב שלישי התחיל, ואז המתזמר עצר את התהליך בגבול הזמן. פירוט הבדיקה והפלטים החלקיים לא נשמרו במעטפת הישנה, ולכן אי אפשר לזהות בדיעבד את הפריט המדויק שהכשיל אותה.
3. מעטפת ה־TIMEOUT הישנה יצרה פלט ללא `run_id`, `system` ו־`request_id`, ואיפסה מונים. לכן הסיכום המקורי מציג בטעות אפס קריאות וחוסר הוכחה למודל, אף שהאירועים מאשרים 28 תשובות אמיתיות. זה פגם בייצוא שלנו, ולא סימן שהמודל לא הופעל. ראיות הניסיון המקוריות לא שוכתבו.
4. ניטור הטוקנים השמיט את השם `prompt_token_count` שבו השתמש ספק Gemini. טוקני הקלט של B אינם ניתנים לשחזור מדויק מהייצוא הזה; אין לפרש את האפס המקורי כצריכת קלט אפס. ספירת פלט נצפית היא 10,197 טוקנים, וחלק מהפעילות לא הסתיים.

## Focused implementation changes

B now uses one agent in one structured CrewAI Task, following the same Task/Crew output mechanism already used by C. It keeps all eight tools, the existing Flow, one planner and the same validators. The previous B path used the lightweight agent kickoff mechanism and could incur an additional output-conversion call. This change is intended to make structured output more reliable; its effect on Gemini has not yet been measured.

Repair rounds receive the full previous plan rather than a 6,000-character prefix, plus the actual place facts and travel results already logged in the same run. The prompt asks the planner to preserve valid fields and repair the failed checks. Shared weather instructions now explicitly require JSON `null` for `weather_note` outside the forecast horizon and forbid a WEATHER drop without a RAIN day. No validator was removed or relaxed, and no model output is silently corrected after generation.

The supervisor now retains the last checked draft and completed tool records before interruption. Check events include detailed validation reports. Interrupted results have the required identity fields, observed completed-call/round counts and a partial-usage marker. A timed-out draft still has status TIMEOUT and cannot pass the proof gate. The dedicated runner exports `last_draft.json` when available. SDK token-count aliases are normalized, and missing token counts remain unknown in monitoring rather than being displayed as zero. Prompts and private model reasoning are not exported.

All changes are in the shared runtime used by the main notebook as well as the proof notebook. The total limits remain three planning rounds and 270 seconds per system. No GM, reviewer or additional agent was added.

## בדיקות ומגבלות

- **139 בדיקות מקומיות עברו**, וגם בדיקת ה־API ללא מודל עברה כמצופה. היומנים נמצאים ב־[`evidence/task2/20261027-second-run-fix`](../evidence/task2/20261027-second-run-fix). בדיקות חדשות מכסות שמירת פלט בזמן עצירה, ספירת תשובות מודל, שמירת סוף תוכנית ארוכה במשוב ומבנה של סוכן יחיד ומשימה מובנית אחת ב־B.
- בדיקות מקומיות משתמשות במודל מדומה או בתהליך מדומה רק בתוך הבדיקות. לא בוצעה כאן קריאת Gemini חדשה לאחר התיקון. אין להציג את הצלחת הבדיקות כהוכחה ש־B תסיים בהרצה הבאה.
- ב־C חזר אותו מסלול מצומצם, כולל שלוש ארוחות של 90, 75 ו־90 דקות מול ההנחיה של 60 דקות. הבדיקות הקיימות אינן אוכפות זאת. הפער מתועד ולא הוסתר באמצעות שינוי התוצאה. כל התאריכים היו מחוץ לטווח תחזית מזג האוויר.
- שתי הרצות מוצלחות של C אינן מוכיחות יתרון כללי על B; זמני הספק, שגיאותיו, הגדרות ההרצה והיקף המסלול משפיעים על התוצאה.

## המשך משימה 2

הריצו שוב **Runtime → Run all** ב[מחברת ההוכחה](https://colab.research.google.com/github/Noven2155/Travel_Agent/blob/main/notebooks/travel_task2_bc_colab.ipynb). התא הראשון משבט עותק חדש של `main`; אותו סוד Gemini נשאר תקף. יש להעלות את ה־ZIP החדש לשיחה זו.

לאחר שההרצה הממוקדת תיבדק, נוודא גם את המסלול הרגיל ב[מחברת הראשית](https://colab.research.google.com/github/Noven2155/Travel_Agent/blob/main/notebooks/travel_streamlit_colab.ipynb). היא טוענת את אותו קוד משותף. אין עדיין אימות מלא מול Gemini דרך הממשק הראשי. משימה 3 לא נפתחה.

</div>
