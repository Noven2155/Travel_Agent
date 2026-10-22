# archive/

**עברית.** בתיקייה הזו שמורים חומרים מהיקף קודם של הפרויקט, וקבצים שכבר אינם בשימוש. הם נשמרו לרקע ולעקיבות, ולא נמחקו. הקוד, הבדיקות, המחברות וההערכה אינם קוראים אף קובץ מכאן, ואין להסתמך עליהם כמתארים את המערכת הנוכחית. התיעוד העדכני נמצא ב־`docs/` (אפיון, מסמכי בוני הסוכנים) וב־`data/README.md` (נתונים).

| תיקייה | תוכן | למה בארכיון |
|---|---|---|
| `docs/` | `CHARTER.md`, שני תרשימי jpeg, הדגמת HTML | ההיקף הקודם של הפרויקט (לפני השוואת שלוש המערכות) |
| `scripts/` | `build_streamlit_notebook.py`, `package_release.py`, `preview_worker.py` | בניית המחברת לפי מבנה הדרייב הישן; אריזת release ותצוגה מקדימה לאתר הקודם |
| `release/` | `RELEASE_MANIFEST.json` | פלט של `package_release.py` |
| `web/` | `smoke_report.json`, `test_report.txt`, `design_detection.json` | דוחות ישנים מהתצוגה המקדימה, שנקראו רק ע״י `package_release.py` |
| `src_travel_agent/` | `cli.py`, `render.py` | ממשק שורת פקודה ישן; `render.py` שימש רק אותו |

הקבצים הועברו כפי שהם, ולכן הנתיבים בתוכם (למשל ב־`package_release.py`) מתייחסים למיקום הקודם. הם עדיין מופיעים ב־`travel_files_manifest.json` (רשומת הדרייב), ומחברת ההשוואה מדלגת עליהם במבנה מאגר.

**English.** Earlier-scope or no-longer-used material, kept for background and traceability rather than deleted. Nothing here is imported or read by the code, tests, notebooks or eval, and none of it describes the current system. Current docs live in `docs/` (spec, agent specs) and `data/README.md` (data). Files were moved as-is, so paths inside them (e.g. in `package_release.py`) refer to their old locations. They are still listed in `travel_files_manifest.json` (the Drive record); the comparison notebook skips them in repo layout.
