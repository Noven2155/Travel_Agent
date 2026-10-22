"""Build a small Colab launcher; source and data remain uncompressed on Drive."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
nb = nbf.v4.new_notebook()
md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell
nb.cells = [
    md('''# Travel Lab — ממשק Streamlit

פתחי את המחברת ב־Google Colab ובחרי **Runtime → Run all**. אשרי חיבור לדרייב. בתא האחרון יופיע הממשק: בחרי תרחיש, הוסיפי מפתח Gemini בסרגל הצד ולחצי **הרץ השוואה**. ללא מפתח אפשר להריץ את מנוע הקוד.

המחברת קטנה; היא קוראת את הקוד ואת הדאטא מתיקיית `travel` הקיימת בדרייב. אין צורך להעלות קבצים מחדש ואין צורך ב־GPU. זו סביבת הדגמה זמנית: השאירי את Colab מחובר ושמרי את התוצאות דרך כפתורי ההורדה בממשק.'''),
    md('''## 1. חיבור וטעינה

ברירת המחדל היא `My Drive/travel`, ובה `project` ו־`data`. אם שמרת את התיקייה במקום אחר, עדכני את הנתיב. נוצר עותק עבודה זמני; קבצי המקור בדרייב נשארים כפי שהם.'''),
    code('''#@title טעינת הפרויקט והדאטא
DRIVE_TRAVEL_FOLDER = "/content/drive/MyDrive/travel" #@param {type:"string"}

import hashlib, importlib.util, json, os, shutil, sys
from pathlib import Path

if not (3, 10) <= sys.version_info[:2] < (3, 14):
    raise RuntimeError("נדרש Python 3.10–3.13. אפשר לבחור סביבת Colab עם Python 3.12.")
IN_COLAB = bool(importlib.util.find_spec("google.colab")) if importlib.util.find_spec("google") else False
if IN_COLAB:
    from google.colab import drive
    drive.mount("/content/drive")
SOURCE = Path(os.environ.get("TRAVEL_DRIVE_FOLDER", DRIVE_TRAVEL_FOLDER))
WORK = Path(os.environ.get("TRAVEL_STREAMLIT_WORK", "/content/travel_streamlit" if IN_COLAB else "travel_streamlit_runtime"))
PROJECT = WORK / "project"
for relative in ("project/streamlit_app.py", "project/requirements-streamlit.txt", "project/src/travel_agent/streamlit_view.py", "data/inventory.json"):
    if not (SOURCE / relative).is_file():
        raise FileNotFoundError(f"חסר {SOURCE / relative}. ודאי שקובצי Streamlit העדכניים נמצאים בתיקיית travel.")
PROJECT.mkdir(parents=True, exist_ok=True)
for relative in ("src", "web", ".streamlit", "frontend/public/fonts"):
    source = SOURCE / "project" / relative
    if source.is_dir():
        shutil.copytree(source, PROJECT / relative, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for name in ("streamlit_app.py", "requirements-streamlit.txt"):
    shutil.copy2(SOURCE / "project" / name, PROJECT / name)
for relative in ("places", "weather"):
    shutil.copytree(SOURCE / "data" / relative, WORK / "data" / relative, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
for name in ("inventory.json", "README_COMPARISON_DATA_HE.md"):
    shutil.copy2(SOURCE / "data" / name, WORK / "data" / name)
expected = "39a0c9c2b2562062211d884af35cc73b3826926b0c56cb06ea5e428c87167319"
if hashlib.sha256((WORK / "data/inventory.json").read_bytes()).hexdigest() != expected:
    raise RuntimeError("הקטלוג שונה מזה שנבדק. נדרשת בדיקת התרחישים מול הקטלוג המעודכן.")
catalog = json.loads((WORK / "data/inventory.json").read_text())
print("הפרויקט נטען. טיסות:", len(catalog["flights"]), "לינות:", len(catalog["stays"]), "רכבים:", len(catalog["cars"]))
'''),
    md('''## 2. התקנת הספריות

בהפעלה הראשונה ההתקנה עשויה להימשך כמה דקות. אם תיכשל, תופיע הודעה והתא האחרון לא ייפתח.'''),
    code('''#@title התקנת Streamlit ומנועי הסוכנים
import subprocess

install_log = WORK / "install.log"
with install_log.open("w") as handle:
    installed = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(PROJECT / "requirements-streamlit.txt")], stdout=handle, stderr=subprocess.STDOUT)
if installed.returncode:
    print(install_log.read_text()[-4000:])
    raise RuntimeError("ההתקנה לא הושלמה. בדקי את השגיאה והריצי מחדש את התא.")
print("הספריות הותקנו.")
'''),
    md('''## 3. פתיחת הממשק

הממשק יופיע מתחת לתא הזה. מפתח ששמור ב־Colab Secrets בשם `GEMINI_API_KEY` ייטען אם נתת למחברת הרשאה. אפשר גם להזין מפתח בשדה הסיסמה בממשק; אין להדביק אותו בקוד.

ההצגה משתמשת במסגרת הנתמכת של Colab. פתיחה בחלון נפרד דרך פונקציית Colab הישנה אינה משמשת כאן, משום ש־Google מסמנת אותה כלא נתמכת. אם המסגרת נחסמת, הוראות להפעלה בחלון דפדפן מלא נמצאות ב־`project/README_STREAMLIT_HE.md` בדרייב.'''),
    code('''#@title הפעלת Streamlit והצגתו
import time, urllib.request

if "STREAMLIT_PROCESS" in globals() and STREAMLIT_PROCESS.poll() is None:
    STREAMLIT_PROCESS.terminate()
    STREAMLIT_PROCESS.wait(timeout=10)
server_env = dict(os.environ, STREAMLIT_BROWSER_GATHER_USAGE_STATS="false", OTEL_SDK_DISABLED="true", CREWAI_DISABLE_TELEMETRY="true")
if IN_COLAB:
    try:
        from google.colab import userdata
        saved_key = userdata.get("GEMINI_API_KEY")
        if saved_key:
            server_env["GEMINI_API_KEY"] = saved_key
        del saved_key
    except Exception:
        print("אפשר להזין מפתח Gemini בסרגל הצד של הממשק.")
server_log_path = WORK / "streamlit.log"
with server_log_path.open("w") as handle:
    STREAMLIT_PROCESS = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(PROJECT / "streamlit_app.py"), "--server.port", "8501", "--server.address", "0.0.0.0", "--server.headless", "true", "--browser.gatherUsageStats", "false"], cwd=PROJECT, env=server_env, stdout=handle, stderr=subprocess.STDOUT)
server_env.pop("GEMINI_API_KEY", None)
deadline = time.monotonic() + 45
while time.monotonic() < deadline:
    if STREAMLIT_PROCESS.poll() is not None:
        raise RuntimeError("שרת Streamlit נעצר. בדקי שההתקנה הושלמה; קובץ האבחון: " + str(server_log_path))
    try:
        with urllib.request.urlopen("http://127.0.0.1:8501/_stcore/health", timeout=1) as response:
            if response.status == 200:
                break
    except Exception:
        time.sleep(.5)
else:
    STREAMLIT_PROCESS.terminate()
    raise RuntimeError("השרת לא נפתח בזמן שהוקצב. הריצי שוב את התא.")
print("Streamlit פועל. הממשק מופיע מתחת להודעה זו.")
if IN_COLAB:
    from google.colab import output
    output.serve_kernel_port_as_iframe(8501, height=1150, cache_in_notebook=False)
else:
    print("פתחי בדפדפן: http://localhost:8501")
'''),
    md('''## מה נבדק ומה עוד נדרש

מנוע הקוד נבדק בפועל דרך ממשק Streamlit בכל ארבעת התרחישים. תוצאות B/C הן תוצאות הרצה רק לאחר חיבור מודל תקין; ללא מפתח הן מסומנות כטרם הופעלו. זמינות ותאריכים בדאטא כוללים הדמיה, ואין הזמנות אמיתיות.

טעינת הקבצים ופקדי הממשק נבדקים מקומית. אישור הדרייב, תצוגת המסגרת והרצת Gemini אמיתי עדיין דורשים בדיקה בחשבון Colab שלך. אם לא מופיע ממשק, ודאי שתא ההתקנה ותא ההפעלה הסתיימו בהצלחה. להורדה למחשב או לקישור צוות קבוע: `README_STREAMLIT_HE.md`.

מקורות: [ממשק הפלט של Colab](https://github.com/googlecolab/colabtools/blob/main/google/colab/output/_util.py), [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).''')
]
nb.metadata = dict(kernelspec=dict(display_name="Python 3", language="python", name="python3"),
                   language_info=dict(name="python", version="3.12"), colab=dict(name="travel_streamlit_colab.ipynb"),
                   travel_project=dict(interface="Streamlit", data_source="Drive/travel/data", actual_model_verified=False))
for cell in nb.cells:
    if cell.cell_type == "code":
        compile(cell.source, "streamlit-colab", "exec")
nbf.validate(nb)
target = ROOT / "colab_delivery/travel_streamlit_colab.ipynb"
target.parent.mkdir(exist_ok=True)
nbf.write(nb, target)
print(target)
