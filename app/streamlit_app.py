"""Travel Agent UI (Streamlit).  Run:  streamlit run app/streamlit_app.py

(a) Plan a trip: TripRequest form or an eval case -> system A/B/C -> package, daily itinerary + map, weather notes
    with source, what we gave up, check report, tool-call log.
(b) Eval dashboard: results directories -> comparison table, filters, per-case drill-down.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from travel_agent import config as C  # noqa: E402
from travel_agent.checks import place_facts  # noqa: E402
from travel_agent.data_access import get_catalog, get_places  # noqa: E402
from travel_agent.models import RunResult, TripRequest  # noqa: E402
from travel_agent.systems import run  # noqa: E402
from travel_agent.systems.llm import availability, settings  # noqa: E402
from travel_agent.tool_log import ToolLog  # noqa: E402

st.set_page_config(page_title="Travel Agent · צוות 8", page_icon="🧳", layout="wide")

SYSTEMS = {"rules": "A – כללים (rules, ללא LLM)", "single": "B – סוכן יחיד (single agent)", "multi": "C – מולטי-אג'נט (multi-agent)"}
STATUS_COLOR = {"OK_PLAN": "green", "CONFLICT_UNRESOLVED": "orange", "NEEDS_DATA": "blue", "NO_PACKAGE_IN_CATALOG": "blue",
                "INVALID_REQUEST": "red", "TECHNICAL_ERROR": "red", "TIMEOUT": "orange"}
CHECK_HE = {"schema": "סכמה", "budget": "תקציב", "dates": "תאריכים", "capacity": "קיבולת", "car": "רכב", "day_load": "עומס יומי",
            "travel": "זמני נסיעה", "weather_rule": "מזג אוויר", "coverage": "כיסוי העדפות", "grounding": "עיגון (grounding)"}
DAY_COLORS = [[230, 25, 75], [60, 180, 75], [0, 130, 200], [245, 130, 48], [145, 30, 180], [70, 240, 240], [240, 50, 230]]


@st.cache_data
def load_cases() -> list[dict]:
    return json.loads((C.CASES_PATH_V2 if C.CASES_PATH_V2.exists() else C.CASES_PATH).read_text())["cases"]


@st.cache_resource
def catalog():
    return get_catalog()


def result_dirs() -> list[Path]:
    return sorted([p for p in C.RESULTS_DIR.glob("*/*") if (p / "run_meta.json").exists()], reverse=True)


# ----------------------------------------------------------------- plan rendering (shared by both pages)
def show_result(r: RunResult, key: str = "res") -> None:
    color = STATUS_COLOR.get(r.status.value, "gray")
    st.markdown(f"### סטטוס: :{color}[{r.status.value}]  ·  מערכת {r.system}  ·  בקשה {r.request_id}")
    if r.message:
        st.caption(r.message)
    m = st.columns(5)
    m[0].metric("זמן ריצה (s)", f"{r.wall_time_s:.2f}")
    m[1].metric("קריאות LLM", r.llm_calls)
    m[2].metric("טוקנים", r.tokens_in + r.tokens_out)
    m[3].metric("סבבים", r.rounds_used)
    m[4].metric("weather_status", r.weather_status.value)
    log = ToolLog(r.run_id)
    log.entries = r.tool_log
    facts = place_facts(log)
    tabs = st.tabs(["חבילה", "מסלול יומי ומפה", "מזג אוויר", "על מה ויתרנו", "דוח בדיקות", "יומן כלים"])
    with tabs[0]:
        if not r.package:
            st.info("אין חבילה – הסטטוס נקבע בקוד לפני שלב ההחלטה." if r.status.value != "OK_PLAN" else "")
        else:
            p = r.package
            fo, fb, s, car = p.flight_out or {}, p.flight_back or {}, p.stay or {}, p.car
            budget = r.request.budget_usd if r.request else None
            st.markdown(f"**סה\"כ:** ${p.total:,.2f}" + (f" מתוך תקציב ${budget:,}" if budget else "") +
                        f"  ·  `price_call_id={p.price_call_id}`  ·  fees_complete={p.fees_complete}")
            rows = [dict(item="✈️ הלוך", ref=p.refs.get("flight_out"), detail=f"{fo.get('origin')}→{fo.get('destination')} {fo.get('dep', '')[:16]} → {fo.get('arr', '')[11:16]} · {fo.get('airline') or ''} · stops={fo.get('stops')}", price=fo.get("fare")),
                    dict(item="✈️ חזור", ref=p.refs.get("flight_back"), detail=f"{fb.get('origin')}→{fb.get('destination')} {fb.get('dep', '')[:16]} → {fb.get('arr', '')[11:16]} · {fb.get('airline') or ''}", price=fb.get("fare")),
                    dict(item="🏠 לינה", ref=p.refs.get("stay"), detail=f"{s.get('title', '')} · {s.get('km_to_center')} ק\"מ מהמרכז · capacity {s.get('capacity')}", price=s.get("price_per_night"))]
            if car:
                rows.append(dict(item="🚗 רכב", ref=p.refs.get("car"), detail=f"{car.get('make')} {car.get('model')} ({car.get('vehicle_type')}) · קיבולת משוערת {car.get('estimated_capacity')} (estimate) · {car.get('rental_days')} ימים", price=car.get("daily_rate")))
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.markdown("**שורות מחיר:** " + " · ".join(f"{k}: ${v:,.2f}" for k, v in p.price_lines.items()))
            if r.candidates:
                with st.expander(f"top-{len(r.candidates)} מועמדים (build_candidates, מתוך {r.candidates[0].get('n_within_budget')} צירופים בתקציב)"):
                    st.dataframe(pd.DataFrame([dict(rank=i + 1, total=c["total"], km_to_center=c["km_to_center"], stops=c["stops"], **c["refs"])
                                               for i, c in enumerate(r.candidates)]), hide_index=True, width="stretch")
    with tabs[1]:
        if not r.days:
            st.info("אין מסלול.")
        else:
            rows = []
            for d in r.days:
                for it in d.items:
                    f = facts.get(it.place_id, {})
                    rows.append(dict(date=d.date, start=it.start, end=it.end, kind=it.kind, name=it.name or f.get("name"),
                                     category=f.get("category"), tags=", ".join(f.get("tags", [])), indoor=f.get("indoor"),
                                     mode=it.mode, travel_min=it.travel_min, place_id=it.place_id, travel_call_id=it.travel_call_id))
            for d in r.days:
                fl = ", ".join(d.flags) if d.flags else ""
                win = f" · חלון {d.window[0]}–{d.window[1]}" if d.window else ""
                st.markdown(f"**{d.date}** {('· ' + fl) if fl else ''}{win} · {len(d.items)} פריטים")
                sub = [x for x in rows if x["date"] == d.date]
                if sub:
                    st.dataframe(pd.DataFrame(sub).drop(columns=["date"]), hide_index=True, width="stretch")
            show_map(r, facts, key)
    with tabs[2]:
        st.caption("מקור: Open-Meteo Historical Forecast API · CC BY 4.0. ימים מעבר ל-7 ימים מ-as_of מסומנים OUT_OF_HORIZON ואין להם טקסט תחזית.")
        st.dataframe(pd.DataFrame([dict(date=c.date, lead_days=c.lead_days, flags=", ".join(c.flags), precip_mm=c.precip_mm, precip_h=c.precip_h,
                                        apparent_max=c.apparent_max, gust_max=c.gust_max, source=c.source) for c in r.day_conditions]),
                     hide_index=True, width="stretch")
    with tabs[3]:
        if r.tradeoffs:
            for t in r.tradeoffs:
                st.markdown(f"- {t}")
        if r.dropped:
            st.dataframe(pd.DataFrame([dict(place_id=x.place_id, name=facts.get(x.place_id, {}).get("name"), reason=x.reason,
                                            indoor=facts.get(x.place_id, {}).get("indoor"), tags=", ".join(facts.get(x.place_id, {}).get("tags", [])))
                                       for x in r.dropped]), hide_index=True, width="stretch")
        if not r.tradeoffs and not r.dropped:
            st.write("—")
    with tabs[4]:
        cr = r.check_report
        if not cr:
            st.info("אין דוח בדיקות (אין תוכנית).")
        else:
            st.markdown(f"coverage = **{cr.coverage}** · ימי גשם: {', '.join(cr.rain_days) or '—'}")
            st.dataframe(pd.DataFrame([dict(check=c.name, בדיקה=CHECK_HE.get(c.name, c.name), passed="✅" if c.passed else "❌",
                                            details="; ".join(c.details[:5])) for c in cr.checks]), hide_index=True, width="stretch")
    with tabs[5]:
        st.caption(f"{len(r.tool_log)} קריאות כלים · כל פלט נושא call_id / source / license / data_date")
        st.dataframe(pd.DataFrame([dict(call_id=e["call_id"], tool=e["tool"], actor=e.get("actor"), source=e["output"].get("source"),
                                        license=e["output"].get("license"), data_date=e["output"].get("data_date"),
                                        args=json.dumps(e["args"], ensure_ascii=False)[:160]) for e in r.tool_log]),
                     hide_index=True, width="stretch")
        pick = st.selectbox("פלט מלא של קריאה", [e["call_id"] for e in r.tool_log], key=f"{key}_call")
        if pick:
            st.json(next(e for e in r.tool_log if e["call_id"] == pick)["output"], expanded=False)


def show_map(r: RunResult, facts: dict, key: str) -> None:
    import pydeck as pdk
    pts, paths = [], []
    s = (r.package.stay or {}) if r.package else {}
    if s.get("lat"):
        pts.append(dict(name="🏠 " + (s.get("title") or "lodging"), lat=s["lat"], lon=s["lon"], color=[0, 0, 0], r=120, label="לינה"))
    for i, d in enumerate(r.days):
        col = DAY_COLORS[i % len(DAY_COLORS)]
        path = [[s["lon"], s["lat"]]] if s.get("lat") else []
        for it in d.items:
            f = facts.get(it.place_id)
            if not f:
                continue
            pts.append(dict(name=f"{d.date} {it.start} {f['name']}", lat=f["lat"], lon=f["lon"], color=col, r=80, label=d.date))
            path.append([f["lon"], f["lat"]])
        if len(path) > 1:
            paths.append(dict(path=path, color=col, name=d.date))
    if not pts:
        return
    df = pd.DataFrame(pts)
    layers = [pdk.Layer("ScatterplotLayer", df, get_position="[lon, lat]", get_fill_color="color", get_radius="r", pickable=True)]
    if paths:
        layers.append(pdk.Layer("PathLayer", pd.DataFrame(paths), get_path="path", get_color="color", width_min_pixels=3, pickable=True))
    view = pdk.ViewState(latitude=float(df.lat.mean()), longitude=float(df.lon.mean()), zoom=11)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, tooltip={"text": "{name}"}, map_style=None), key=f"{key}_map")
    st.caption("מפה: נקודה שחורה = לינה; צבע לכל יום. מקומות © OpenStreetMap contributors (ODbL).")


# ----------------------------------------------------------------- page (a)
def page_plan() -> None:
    st.header("🧳 תכנון טיול · Plan a trip")
    cases = load_cases()
    cat = catalog()
    left, right = st.columns([1, 2])
    with left:
        src = st.radio("מקור הבקשה", ["בקשת eval", "טופס חופשי"], horizontal=True)
        case = None
        if src == "בקשת eval":
            labels = {c["id"]: f"{c['id']} · {c['group']} · {c['city']} · {c['origin']} {c['start_date']}→{c['end_date']} · {c['conflict_description'][:40]}" for c in cases}
            cid = st.selectbox("בקשה", list(labels), format_func=lambda x: labels[x], index=0)
            case = next(c for c in cases if c["id"] == cid)
            st.caption(f"expected_status: **{case['expected_status']}** · split {case['split']}")
        d0 = case or dict(city="Chicago", origin="LGA", start_date="2022-10-26", end_date="2022-10-29", travelers=1, budget_usd=900,
                          wants_car=False, pace="normal", interests=["culture", "food"], avoid=[], hotel_preference="any",
                          as_of="2022-09-26", free_text="")
        with st.form("trip"):
            city = st.selectbox("עיר", list(C.CITIES), index=list(C.CITIES).index(d0["city"]),
                                help="ניו יורק: נתוני המקומות עדיין בבנייה → NEEDS_DATA" if get_places("New York") is None else None)
            origin = st.selectbox("מוצא (IATA)", cat.origins, index=cat.origins.index(d0["origin"]))
            c1, c2 = st.columns(2)
            start = c1.date_input("יציאה", dt.date.fromisoformat(d0["start_date"]), min_value=dt.date(2022, 4, 17), max_value=dt.date(2022, 11, 19))
            end = c2.date_input("חזרה", dt.date.fromisoformat(d0["end_date"]), min_value=dt.date(2022, 4, 17), max_value=dt.date(2022, 11, 19))
            c3, c4 = st.columns(2)
            travelers = c3.number_input("נוסעים", 1, 6, int(d0["travelers"]))
            budget = c4.number_input("תקציב לקבוצה ($)", 100, 50000, int(d0["budget_usd"]), step=10)
            wants_car = st.radio("לתכנן השכרת רכב? (נכלל בתקציב)", ["לא", "כן"], index=1 if d0["wants_car"] else 0, horizontal=True) == "כן"
            pace = st.select_slider("קצב", ["relaxed", "normal", "packed"], value=d0["pace"])
            interests = st.multiselect("תחומי עניין (1–4)", C.VOCAB, default=d0["interests"], max_selections=4)
            avoid = st.multiselect("להימנע", C.VOCAB, default=d0["avoid"])
            central = st.checkbox("לינה מרכזית (עד 5 ק\"מ מה-Loop / 6 ק\"מ מ-Times Square)", value=d0["hotel_preference"] == "central")
            as_of = st.date_input("as_of (\"היום\" של הבקשה – קובע את אופק התחזית)", dt.date.fromisoformat(d0["as_of"]))
            free_text = st.text_input("טקסט חופשי (רק לסוכנים B/C)", d0.get("free_text") or "")
            system = st.radio("מערכת", list(SYSTEMS), format_func=SYSTEMS.get)
            go = st.form_submit_button("תכנן 🚀", type="primary")
        if system != "rules":
            ok, why = availability()
            (st.success if ok else st.warning)(f"LLM ({settings()['model']}): {why}")
    with right:
        if go:
            raw = dict(request_id=case["id"] if case else "UI", city=city, origin=origin, start_date=start.isoformat(),
                       end_date=end.isoformat(), travelers=int(travelers), budget_usd=int(budget), wants_car=wants_car, pace=pace,
                       interests=interests, avoid=avoid, hotel_preference="central" if central else "any", as_of=as_of.isoformat(),
                       free_text=free_text or None)
            with st.spinner("מתכנן..."):
                st.session_state["plan_result"] = run(system, raw)
        if "plan_result" in st.session_state:
            show_result(st.session_state["plan_result"], key="plan")
        else:
            st.info("בחרו בקשה ומערכת ולחצו 'תכנן'. מערכת A (כללים) רצה בלי LLM.")


# ----------------------------------------------------------------- page (b)
def page_eval() -> None:
    from eval.score import in_D, is_valid, per_case_rows, render, summarize
    st.header("📊 לוח הערכה · Eval dashboard")
    dirs = result_dirs()
    if not dirs:
        st.warning("אין תוצאות. הריצו: python -m eval.run_eval --system rules --split eval --city chicago")
        return
    rel = [str(d.relative_to(C.REPO_ROOT)) for d in dirs]
    latest = {}
    for d in rel:
        latest.setdefault(d.split("/")[2], d)
    chosen = st.multiselect("תיקיות תוצאות (אחת לכל מערכת)", rel, default=list(latest.values()))
    if not chosen:
        return
    c1, c2 = st.columns(2)
    c1.multiselect("סינון לפי קבוצה", list("ABCDE"), key="f_groups")
    c2.multiselect("סינון לפי עיר", list(C.CITIES), key="f_cities")
    all_recs, rows = [], []
    for d in chosen:
        p = C.REPO_ROOT / d
        meta = json.loads((p / "run_meta.json").read_text())
        recs = [json.loads(x.read_text()) for x in sorted(p.glob("*.json")) if x.name != "run_meta.json"]
        f1, f2 = st.session_state.get("f_groups"), st.session_state.get("f_cities")
        if f1:
            recs = [r for r in recs if r["case"]["group"] in f1]
        if f2:
            recs = [r for r in recs if r["case"]["city"] in f2]
        if recs:
            meta["_dir"] = d
            rows.append(summarize(meta, recs))
            all_recs += recs
    if not rows:
        st.info("אין בקשות אחרי הסינון.")
        return
    md, csv_rows = render(sorted(rows, key=lambda s: s["system"]))
    st.subheader("טבלת השוואה")
    st.markdown(md)
    st.caption("valid_plan = OK_PLAN ∧ כל final_checks עוברות ∧ זמן ≤ 300s ∧ סבבים ≤ 3. D = בקשות eval בקבוצות A–D עם oracle פתיר (מתוך הבקשות שבריצה).")
    pc = pd.DataFrame(per_case_rows(all_recs))
    st.subheader("פירוט לפי בקשה")
    st.dataframe(pc, hide_index=True, width="stretch")
    st.subheader("Drill-down")
    opts = [f"{r['system']} · {r['case']['id']}" for r in all_recs]
    pick = st.selectbox("בקשה", opts)
    if pick:
        rec = all_recs[opts.index(pick)]
        st.caption(f"expected={rec['case']['expected_status']} · in_D={in_D(rec)} · valid_plan={is_valid(rec)} · {rec['case']['conflict_description']}")
        show_result(RunResult.model_validate(rec), key="drill")


def main() -> None:
    st.sidebar.title("Travel Agent")
    st.sidebar.caption("BIU DS23 · צוות 8 · CrewAI 1.15 Flow")
    page = st.sidebar.radio("עמוד", ["תכנון טיול", "לוח הערכה"])
    st.sidebar.markdown("---")
    st.sidebar.caption("נתונים: OpenStreetMap (ODbL), Wikivoyage (CC BY-SA), Open-Meteo (CC BY 4.0), Inside Airbnb (CC BY 4.0), "
                       "Kaggle flights/cars. דירוגים, ביקורות, משך ביקור ורוב רמות המחיר במקומות – סינתטיים ואינם בשימוש לעיגון.")
    if page == "תכנון טיול":
        page_plan()
    else:
        page_eval()


main()
