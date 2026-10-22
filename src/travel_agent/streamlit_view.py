"""Hebrew Streamlit comparison surface over the actual A/B/C systems."""
from __future__ import annotations

import base64
import copy
import datetime as dt
import html
import json
import os
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

from .streamlit_service import ComparisonJob, LABELS, locate_data, metric_rows, metrics_csv

STATUS = {"OK_PLAN": "תוכנית תקינה", "NO_PACKAGE_IN_CATALOG": "אין חבילה בתנאים האלה",
          "CONFLICT_UNRESOLVED": "נותרו אילוצים לפתרון", "NEEDS_DATA": "חסר מידע לאימות",
          "INVALID_REQUEST": "יש לתקן את הבקשה", "TECHNICAL_ERROR": "שגיאת הרצה", "TIMEOUT": "הזמן שהוקצב הסתיים"}
PACE = {"relaxed": "רגוע", "normal": "רגיל", "packed": "אינטנסיבי"}
ACTOR = {"trip_manager": "סוכן החבילה", "places": "סוכן המקומות", "itinerary": "סוכן המסלול", "TripPlanner": "הסוכן המתכנן"}
CITY = {"Chicago": "שיקגו", "New York": "ניו יורק"}
INTEREST = {"culture": "תרבות", "food": "אוכל", "nature": "טבע", "attractions": "אטרקציות"}
PREFERENCE = {"central": "לינה עד 6 ק״מ מהמרכז", "nonstop": "טיסה ישירה",
              "dry_days": "ימים יבשים", "exact_dates": "שמירת התאריכים המקוריים"}


def approved_request(case, values):
    request = copy.deepcopy(case["request"])
    for key in ("budget_usd", "travelers", "pace", "wants_car", "city", "origin"):
        request[key] = values["field_" + key]
    request.update(start_date=values["field_start"].isoformat(), end_date=values["field_end"].isoformat())
    changed = any(request[k] != case["request"][k] for k in request)
    if not changed:
        text = case["request_text"]
    else:
        interests = ", ".join(INTEREST.get(k, k) for k in request["interests"])
        text = (f'אנחנו {request["travelers"]} מטיילים. נצא מ־{request["origin"]} ל{CITY[request["city"]]} '
                f'מ־{request["start_date"]} עד {request["end_date"]}. תקרת תקציב לקבוצה: '
                f'{request["budget_usd"]:,} דולר לטיסות ולינה' + (" ורכב. " if request["wants_car"] else ". בלי רכב. ") +
                f'תחומי עניין: {interests}. קצב: {PACE[request["pace"]]}. ')
        text += (f'גמישות ביציאה: {request["depart_flex_days"]} ימים; '
                 f'בחזרה: {request["return_flex_days"]} ימים. ')
        if request.get("soft_prefs"):
            text += "עדיפויות: " + "; ".join(
                f'{PREFERENCE.get(k, k)} (משקל {request.get("priority_weights", {}).get(k, 1):g})'
                for k in request["soft_prefs"]) + "."
    request["free_text"] = text
    return request, text


def money(value):
    return "—" if value is None else f"${value:,.2f}"


def skin(root):
    face = ""
    for name, weight in (("Regular", 400), ("Bold", 700)):
        font = root / "frontend/public/fonts" / f"NotoSansHebrew-{name}.ttf"
        if font.is_file():
            encoded = base64.b64encode(font.read_bytes()).decode()
            face += "@font-face{font-family:Noto;font-weight:" + str(weight) + ";src:url(data:font/ttf;base64," + encoded + ") format('truetype');font-display:swap;}"
    st.html("<style>" + face + '''
    html,body,[data-testid="stAppViewContainer"]{color:#102b43;background:#fff;}
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"]{direction:rtl;font-family:Noto,Arial,sans-serif;}
    [data-testid="stMainBlockContainer"]{max-width:1480px;padding-top:2.2rem;padding-bottom:3rem;}
    [data-testid="stSidebar"]{background:#f5f8fb;border-right:1px solid #dce4ec;}
    h1,h2,h3,p,label,button,input,textarea{font-family:Noto,Arial,sans-serif!important;}
    h1{font-size:clamp(36px,3.7vw,56px)!important;line-height:1.3!important;letter-spacing:-.02em;}
    h2{font-size:21px!important;margin-top:.5rem!important;}
    h3{font-size:20px!important;}
    p{line-height:1.8;}
    [data-testid="stCaptionContainer"]{color:#536779;}
    [data-testid="stMetricValue"]{font-size:24px!important;font-variant-numeric:tabular-nums;direction:ltr;text-align:right;}
    [data-testid="stMetricLabel"]{font-size:.85rem;}
    [data-testid="stTextArea"] textarea{line-height:1.8;}
    [data-testid="stButton"] button,[data-testid="stDownloadButton"] button{min-height:44px;border-radius:6px;}
    [data-testid="stTextInput"] input{direction:ltr;text-align:left;}
    :focus-visible{outline:3px solid #91b3ff!important;outline-offset:3px;}
    ::selection{background:#e3eafb;color:#102b43;}
    input,textarea{caret-color:#2559cb;}
    a{text-underline-offset:3px;color:#2559cb;}
    .travel-status{font-size:.85rem;padding:8px 10px;background:#f4f7fa;margin:6px 0 16px;border-radius:4px;}
    .travel-status.good{background:#eff7f2;color:#267058;}
    .travel-status.waiting{background:#faf5e9;color:#755219;}
    .travel-route{direction:ltr;text-align:right;font-size:.95rem;font-variant-numeric:tabular-nums;}
    .travel-summary{font-size:.95rem;color:#536779;margin-bottom:1.25rem;}
    [data-testid="stTabs"] button p{font-size:.95rem;}
    @media(max-width:700px){[data-testid="stMainBlockContainer"]{padding-top:1.2rem;padding-inline:1rem;}h1{font-size:36px!important;}}
    @media(prefers-reduced-motion:reduce){*{animation-duration:.01ms!important;transition-duration:.01ms!important;}}
    </style>''')


def badge(text, state=""):
    st.html(f'<div class="travel-status {state}">{html.escape(text)}</div>')


def choose_case(cases):
    case = next(c for c in cases if c["id"] == st.session_state.case_id)
    req = case["request"]
    for key in ("budget_usd", "travelers", "pace", "wants_car", "city", "origin"):
        st.session_state["field_" + key] = req[key]
    st.session_state.field_start = dt.date.fromisoformat(req["start_date"])
    st.session_state.field_end = dt.date.fromisoformat(req["end_date"])
    st.session_state.request_text = case["request_text"]


def model_panel(busy):
    with st.sidebar:
        st.title("Travel Lab")
        page = st.radio("תצוגה", ["השוואת מערכות", "הנתונים"], label_visibility="collapsed")
        st.divider()
        st.subheader("חיבור המודל")
        try:
            saved = st.secrets.get("GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        except Exception:
            saved = os.environ.get("GEMINI_API_KEY", "")
        key = st.text_input("מפתח Gemini", type="password", key="gemini_key", disabled=busy,
                            help="המפתח נשמר בזיכרון של החיבור הנוכחי ומשמש רק להרצות שתפעילו.")
        key = key.strip() or saved
        model = st.text_input("שם המודל", value="gemini-3.1-flash-lite", disabled=busy, key="gemini_model")
        if key:
            st.caption("מפתח זמין. תקינותו תיבדק בהפעלה.")
        else:
            st.caption("אפשר להתחיל עם מנוע הקוד. הוספת מפתח תאפשר את מערכות B ו־C.")
        with st.expander("הגדרות ההשוואה"):
            measure = st.selectbox("אופן ההרצה", ["במקביל — להצגה", "בנפרד — למדידה"], disabled=busy)
            natural = st.checkbox("פענוח טקסט לסוכנים", disabled=busy,
                                  help="B/C יפענחו את הטקסט. הבדיקה עדיין תוודא שהן עומדות בשדות המשותפים שאישרתם.")
            st.caption("אומדן עלות המודל מחושב רק אם מזינים את התעריפים מהחשבון.")
            in_rate = st.number_input("דולר למיליון טוקני קלט", min_value=0., value=0., step=.05, disabled=busy)
            out_rate = st.number_input("דולר למיליון טוקני פלט", min_value=0., value=0., step=.05, disabled=busy)
            price_known = st.checkbox("התעריפים הוזנו ונבדקו", disabled=busy)
        st.divider()
        st.caption("נתוני קטלוג היסטוריים וזמינות מדומה. עלויות ביקור, ארוחות ועמלות חסרות אינן כלולות במחיר החבילה.")
    credentials = {"LLM_MODEL": "gemini/" + model.removeprefix("gemini/"), "GEMINI_API_KEY": key} if key else {}
    pricing = dict(input_per_million=in_rate, output_per_million=out_rate) if price_known else {}
    return page, credentials, "benchmark_isolated" if measure.startswith("בנפרד") else "demo_parallel", "natural" if natural else "structured", pricing


def package_view(result):
    package = result.get("package")
    if not package:
        st.caption("לא נבחרה חבילה.")
        if result.get("message"):
            st.caption(result["message"])
        return
    for name, field in [("טיסת הלוך", "flight_out"), ("טיסת חזור", "flight_back")]:
        flight = package.get(field) or {}
        st.markdown("**" + name + "**")
        route = f'{flight.get("origin", "")} → {flight.get("destination", "")}'
        st.html('<div class="travel-route">' + html.escape(route) + '</div>')
        st.caption(f'{str(flight.get("dep", ""))[:16]} · {flight.get("airline") or ""} · {flight.get("stops", "—")} עצירות')
    stay = package.get("stay") or {}
    st.markdown("**לינה**")
    st.write(stay.get("title") or "מקום לינה מהקטלוג")
    st.caption(f'{stay.get("km_to_center", "—")} ק״מ מהמרכז · קיבולת {stay.get("capacity", "—")}')
    if stay.get("lat") is not None and stay.get("lon") is not None:
        st.link_button("פתיחה ב־Google Maps", "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": f'{stay["lat"]},{stay["lon"]}'}))
    car = package.get("car")
    if car:
        st.markdown("**רכב**")
        st.write(f'{car.get("make", "")} {car.get("model", "")}')
        st.caption(f'קיבולת משוערת: {car.get("estimated_capacity", "—")} · מחיר ליום: {money(car.get("daily_rate"))}')
    with st.expander("פירוט מחיר ופשרות"):
        names = {"flights": "טיסות לקבוצה", "lodging": "לינה", "car": "רכב"}
        for k, v in package.get("price_lines", {}).items():
            st.write(f"{names.get(k, k)}: {money(v)}")
        for note in result.get("tradeoffs", []):
            st.write("• " + note)


def itinerary_view(result):
    if not result.get("days"):
        st.info("אין מסלול להצגה בהרצה הזאת.")
        return
    points = []
    for day in result["days"]:
        with st.expander(day["date"], expanded=True):
            for item in day.get("items", []):
                st.markdown(f'**{item.get("start", "")}–{item.get("end", "")}** · {item.get("name") or item.get("place_id", "")}')
                st.caption(f'מעבר: {item.get("travel_min", "—")} דקות · {item.get("mode", "")}')
    for call in result.get("tool_log", []):
        payload = call.get("output") or call.get("result") or {}
        if isinstance(payload, dict):
            for place in payload.get("places", []):
                if place.get("lat") is not None and place.get("lon") is not None:
                    points.append(dict(lat=place["lat"], lon=place["lon"]))
    if points:
        with st.expander("מפת המקומות שעלו בחיפוש"):
            st.map(pd.DataFrame(points).drop_duplicates())


def show_result(data, history, partial=False):
    st.subheader("תוצאות שכבר התקבלו" if partial else "תוצאות ההשוואה")
    if data["mode"] == "baseline_check":
        st.caption("בוצעה הרצה אמיתית של A בלבד. B ו־C ממתינות לחיבור מודל.")
    cols = st.columns(3, gap="large")
    for col, (key, label) in zip(cols, LABELS.items()):
        with col:
            st.markdown("### " + label)
            slot = data.get("runs", {}).get(key)
            if not slot:
                if partial:
                    badge("ההרצה טרם הסתיימה", "waiting")
                    st.caption("התוצאה תוצג כאן ברגע שהמערכת תסיים.")
                    continue
                badge("ממתין לחיבור מודל", "waiting")
                st.caption("הוסיפו מפתח Gemini בסרגל הצד והריצו השוואה חדשה.")
                continue
            result, metrics = slot.get("result") or {}, slot.get("metrics") or {}
            status = STATUS.get(result.get("status"), result.get("status") or "ממתין")
            badge(status, "good" if metrics.get("valid_plan") else "waiting")
            st.metric("מחיר החבילה לקבוצה", money(metrics.get("package_usd")))
            seconds = metrics.get("time_s")
            st.caption(f'משך הרצה: {seconds:.2f} שניות' if seconds is not None else "משך הרצה: —")
            st.caption(f'קריאות מודל שהתחילו: {metrics.get("llm_calls_attempted", metrics.get("llm_calls", 0))} · בדיקות: {metrics.get("checks_passed", 0)}/{metrics.get("checks_total", 0)}')
            if result.get("status") in ("TECHNICAL_ERROR", "TIMEOUT"):
                message = result.get("message") or (slot.get("monitoring") or {}).get("error_detail")
                if message:
                    st.error(str(message)[:1800])
    tabs = st.tabs(["החבילות", "מסלולי הטיול", "המדדים", "תהליך העבודה"])
    with tabs[0]:
        for col, (key, label) in zip(st.columns(3, gap="large"), LABELS.items()):
            with col:
                st.markdown("**" + label + "**")
                slot = data.get("runs", {}).get(key)
                if slot:
                    package_view(slot.get("result") or {})
                else:
                    st.caption("ההרצה טרם הסתיימה" if partial else "טרם הופעלה")
    available = list(data.get("runs", {}))
    with tabs[1]:
        key = st.selectbox("מסלול של מערכת", available, format_func=lambda k: LABELS[k], key="itinerary_system")
        itinerary_view(data["runs"][key].get("result") or {})
    with tabs[2]:
        rows = []
        for row in metric_rows(data):
            rows.append({"מערכת": row["system_name"], "תוצאה": STATUS.get(row["status"], "טרם הסתיימה" if partial else "לא הופעלה"),
                         "תוכנית תקינה": row.get("valid_plan"), "מחיר ($)": row.get("package_usd"),
                         "שניות": row.get("time_s"), "כיסוי העדפות": row.get("interests_coverage"),
                         "התאמה להעדפות רכות": row.get("soft_satisfaction"), "קריאות כלים": row.get("tool_calls"),
                         "קריאות מודל שהתחילו": row.get("llm_calls_attempted", row.get("llm_calls")),
                         "קריאות מודל שנכשלו": row.get("llm_calls_failed"),
                         "טוקני קלט": row.get("tokens_in"), "טוקני פלט": row.get("tokens_out"),
                         "אומדן עלות מודל ($)": row.get("estimated_llm_cost_usd")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("תוכנית תקינה עומדת באילוצים ובבדיקות, בתוך 5 דקות ועד 3 סבבים. זיהוי נכון של היעדר חבילה נבחן בנפרד ממציאת תוכנית. אלו מדדים מהריצה; נדרש אוסף הרצות כדי לחשב שיעורי הצלחה.")
        st.download_button("הורדת טבלת המדדים", metrics_csv(history), "travel_metrics.csv", "text/csv")
    with tabs[3]:
        key = st.selectbox("תהליך של מערכת", available, format_func=lambda k: LABELS[k], key="evidence_system")
        result = data["runs"][key].get("result") or {}
        checks = (result.get("check_report") or {}).get("checks", [])
        st.dataframe(pd.DataFrame([{ "בדיקה": c["name"], "עברה": c["passed"], "פרטים": "; ".join(map(str, c.get("details", [])))} for c in checks]), hide_index=True, width="stretch")
        with st.expander("אירועי סוכנים וקריאות כלים"):
            st.json(dict(events=data["runs"][key].get("events", [])[-80:], tool_log=result.get("tool_log", [])))
        st.download_button("הורדת ההרצה המלאה", json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), "travel_comparison.json", "application/json")


def duration(value):
    if value is None:
        return "—"
    minutes, seconds = divmod(int(value), 60)
    return f"{minutes:02}:{seconds:02}"


def live_monitor(progress):
    for col, (key, label) in zip(st.columns(3, gap="large"), LABELS.items()):
        with col:
            item = progress.get(key) or {}
            st.markdown("### " + label)
            st.write({"waiting": "ממתינה", "running": "פועלת", "complete": "הסתיימה"}.get(item.get("state"), "מתחילה"))
            st.write(item.get("current_action", "מכינה את סביבת ההרצה"))
            if item.get("actor"):
                st.caption(ACTOR.get(item["actor"], item["actor"]))
            st.markdown(f'**זמן ריצה: {duration(item.get("elapsed_s"))}**')
            if item.get("state") == "running":
                st.caption(f'בפעולה הנוכחית: {duration(item.get("action_elapsed_s"))} · נותרו: {duration(item.get("remaining_s"))}')
                st.caption(f'ללא עדכון חדש: {duration(item.get("idle_s"))}')
            st.write(f'מודל: {item.get("llm_started", 0)} התחילו · {item.get("llm_completed", 0)} הסתיימו · {item.get("llm_failed", 0)} נכשלו')
            st.caption(f'כלים: {item.get("tools_completed", 0)} הסתיימו / {item.get("tools_started", 0)} התחילו · ניסיונות חוזרים: {item.get("retries", 0)}')
            if item.get("tokens_in_observed") is not None:
                st.caption(f'טוקנים שדווחו: {item["tokens_in_observed"]:,} קלט · {item["tokens_out_observed"]:,} פלט')
            if item.get("state") == "running" and (item.get("idle_s") or 0) >= 30:
                st.info("אין עדכון חדש. מונה הזמן ממשיך לפעול; ייתכן שהמערכת ממתינה לתשובת המודל.")
            if item.get("llm_unfinished"):
                st.caption(f'{item["llm_unfinished"]} קריאות נותרו ללא סיום מתועד כשהתהליך נעצר.')
            if item.get("result_status") in ("TECHNICAL_ERROR", "TIMEOUT") and item.get("error_detail"):
                st.error(item["error_detail"][:1800])
    with st.expander("יומן הפעולות ומשך כל קריאת מודל"):
        st.caption("אירועים שנמדדו בפועל. קריאות מודל נספרות בגבולות ספריית המודל; ניסיונות HTTP פנימיים אינם בהכרח נחשפים. טוקנים שדווחו במהלך הרצה הם מידע חלקי. לא מוצגים פרומפטים או תוכן החשיבה של המודל.")
        for key, label in LABELS.items():
            item = progress.get(key) or {}
            st.markdown("**" + label + "**")
            calls = item.get("calls", [])
            if calls:
                st.dataframe(pd.DataFrame([{"קריאה": c["id"], "מודל": c.get("model"), "סוכן": ACTOR.get(c.get("actor"), c.get("actor")),
                    "מצב": {"running": "ממתינה לתשובה", "complete": "הסתיימה", "failed": "נכשלה", "unfinished": "ללא סיום מתועד"}.get(c["status"], c["status"]),
                    "שניות": c.get("duration_s"), "שגיאה": c.get("error", "")} for c in calls]), hide_index=True, width="stretch")
            recent = item.get("recent", [])
            if recent:
                st.dataframe(pd.DataFrame(recent).rename(columns={"time": "זמן (UTC)", "actor": "גורם מבצע", "action": "פעולה", "duration_s": "שניות", "detail": "פרטי שגיאה"}), hide_index=True, width="stretch")
            else:
                st.caption("טרם התקבלו אירועי עבודה.")


def job_panel():
    job = st.session_state.job
    snapshot = job.snapshot()
    if snapshot["state"] == "running":
        st.subheader("ההרצה מתבצעת")
        live_monitor(snapshot["progress"])
        if st.button("עצירת ההרצה", key="cancel_comparison"):
            job.cancel()
        st.session_state.was_running = True
        partial = snapshot.get("partial")
        if partial and partial.get("runs"):
            show_result(partial, job.results + [partial], partial=True)
    else:
        if st.session_state.get("was_running"):
            st.session_state.was_running = False
            st.rerun()
        if snapshot["state"] == "error":
            st.error(snapshot["error"])
        elif snapshot["state"] == "cancelled":
            st.info("ההרצה נעצרה. אפשר לעדכן את הבקשה ולנסות שוב.")
        elif snapshot["result"]:
            show_result(snapshot["result"], job.results)
            with st.expander("מעקב מפורט אחר ההרצה שהסתיימה"):
                live_monitor(snapshot["progress"])
        else:
            st.subheader("מוכנים להשוואה")
            st.caption("בחרו תרחיש ולחצו על כפתור ההרצה. החבילות, המסלולים והמדדים יופיעו כאן.")


def data_page(data_dir):
    st.title("הנתונים של המערכת")
    st.write("שלוש המערכות קוראות מאותו קטלוג. הנתונים נשארים בקבצים נפרדים ואפשר לעיין בהם כאן.")
    inventory = json.loads((data_dir / "inventory.json").read_text())
    kind = st.selectbox("איזה דאטא להציג?", ["flights", "stays", "cars", "chicago", "nyc"],
                        format_func=lambda k: {"flights": "טיסות", "stays": "לינה", "cars": "רכבים", "chicago": "מקומות בשיקגו", "nyc": "מקומות בניו יורק"}[k])
    if kind in inventory:
        rows = inventory[kind]
        frame = pd.DataFrame(rows)
        wanted = [c for c in ["origin", "destination", "city", "airport", "title", "make", "model", "fare", "price_per_night", "daily_rate", "capacity", "estimated_capacity"] if c in frame.columns]
        st.caption(f"{len(rows):,} רשומות · מוצגות 100 ראשונות")
        st.dataframe(frame[wanted].head(100) if wanted else frame.head(100).astype(str), hide_index=True, width="stretch")
        csv_path = data_dir / {"flights": "flights.csv", "stays": "stays.csv", "cars": "cars.csv"}[kind]
        content = csv_path.read_bytes() if csv_path.is_file() else frame.to_csv(index=False).encode("utf-8-sig")
        st.download_button("הורדת כל הרשומות", content, kind + ".csv", "text/csv")
    else:
        path = data_dir / "places" / ("chicago_places.csv" if kind == "chicago" else "nyc_places.csv")
        frame = pd.read_csv(path)
        st.caption(f"{len(frame):,} רשומות · מוצגות 100 ראשונות")
        wanted = [c for c in ["name", "category", "tags", "lat", "lon", "source"] if c in frame.columns]
        st.dataframe(frame[wanted].head(100), hide_index=True, width="stretch")
        st.download_button("הורדת כל הרשומות", path.read_bytes(), path.name, "text/csv")
    with st.expander("מקורות ומגבלות"):
        st.markdown((data_dir / "README_COMPARISON_DATA_HE.md").read_text())


def main(root):
    st.set_page_config(page_title="Travel Lab · השוואת מערכות", layout="wide", initial_sidebar_state="expanded")
    skin(root)
    try:
        data_dir = locate_data(root)
    except FileNotFoundError as exc:
        st.error(str(exc)); st.stop()
    if "job" not in st.session_state:
        st.session_state.job = ComparisonJob(root, data_dir)
    job = st.session_state.job
    busy = job.snapshot()["state"] == "running"
    page, credentials, mode, input_mode, pricing = model_panel(busy)
    if page == "הנתונים":
        data_page(data_dir)
        return
    cases = json.loads((root / "web" / "scenarios.json").read_text())
    if "case_id" not in st.session_state:
        st.session_state.case_id = cases[0]["id"]
        choose_case(cases)
    st.title("תכנון טיול קבוצתי")
    st.write("בקשה אחת, שלוש מערכות. בוחרים תרחיש, מריצים ומשווים את החבילה ואת מסלול הטיול.")
    st.selectbox("תרחיש לבדיקה", [c["id"] for c in cases], format_func=lambda key: next(c["title"] for c in cases if c["id"] == key),
                 key="case_id", on_change=choose_case, args=(cases,), disabled=busy)
    case = next(c for c in cases if c["id"] == st.session_state.case_id)
    st.caption(case["description"])
    request, structured_text = approved_request(case, st.session_state)
    if input_mode == "structured":
        st.session_state.request_text = structured_text
    st.text_area("הבקשה המשותפת", key="request_text", height=130, disabled=busy or input_mode == "structured")
    with st.expander("פרטי הבקשה — שינוי תאריכים, תקציב והעדפות"):
        c1,c2,c3 = st.columns(3)
        with c1:
            inventory = json.loads((data_dir / "inventory.json").read_text())
            origins = sorted({f["origin"] for f in inventory["flights"]})
            st.selectbox("נמל מוצא", origins, key="field_origin", disabled=busy)
            st.selectbox("יעד", list(CITY), format_func=lambda k: CITY[k], key="field_city", disabled=busy)
        with c2:
            st.date_input("יציאה", key="field_start", min_value=dt.date(2022,4,17), max_value=dt.date(2022,11,19), disabled=busy)
            st.date_input("חזרה", key="field_end", min_value=dt.date(2022,4,17), max_value=dt.date(2022,11,19), disabled=busy)
        with c3:
            st.number_input("תקציב לקבוצה ($)", min_value=1, max_value=100000, key="field_budget_usd", disabled=busy)
            st.number_input("מספר מטיילים", min_value=1, max_value=6, key="field_travelers", disabled=busy)
        st.selectbox("קצב הטיול", list(PACE), format_func=lambda k: PACE[k], key="field_pace", disabled=busy)
        st.checkbox("כולל רכב", key="field_wants_car", disabled=busy)
        st.caption("השדות האלה משותפים לשלוש המערכות. שינוי שלהם יוצר בקשה חדשה שאינה בהכרח תואמת לתרחיש המקורי.")
    label = "הרץ השוואה" if credentials else "הרץ את מנוע הקוד"
    if st.button(label, type="primary", key="run_comparison", disabled=busy, width="stretch"):
        request, _ = approved_request(case, st.session_state)
        request["free_text"] = st.session_state.request_text
        try:
            from .models import TripRequest
            TripRequest.model_validate(request)
            job.start(request=request, request_text=st.session_state.request_text, title=case["title"],
                      credentials=credentials, mode=mode, input_mode=input_mode, pricing=pricing, only_rules=not bool(credentials))
            st.rerun()
        except Exception as exc:
            st.error("יש לתקן את פרטי הבקשה: " + str(exc))
    st.divider()
    st.fragment(run_every=1 if busy else None)(job_panel)()
