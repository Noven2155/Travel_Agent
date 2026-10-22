"""render step: user-facing text built in code from a RunResult (no LLM call)."""
from __future__ import annotations

from .checks import place_facts
from .models import RunResult
from .tool_log import ToolLog


def render_markdown(r: RunResult) -> str:
    log = ToolLog(r.run_id)
    log.entries = r.tool_log
    facts = place_facts(log)
    out = [f"# {r.request_id} · system {r.system} · {r.status.value}"]
    if r.message:
        out.append(f"> {r.message}")
    if r.package:
        p = r.package
        out.append(f"\n## Package — ${p.total:,.2f} (price_call_id {p.price_call_id}; fees not included)")
        fo, fb, s = p.flight_out or {}, p.flight_back or {}, p.stay or {}
        out.append(f"- Outbound {p.refs['flight_out']}: {fo.get('origin')}→{fo.get('destination')} {fo.get('dep', '')[:16]} (lands {fo.get('arr', '')[11:16]}), ${fo.get('fare')}/traveler")
        out.append(f"- Return {p.refs['flight_back']}: {fb.get('origin')}→{fb.get('destination')} {fb.get('dep', '')[:16]}, ${fb.get('fare')}/traveler")
        out.append(f"- Lodging {p.refs['stay']}: {s.get('title', '')} · ${s.get('price_per_night')}/night · {s.get('km_to_center')} km from center")
        if p.car:
            out.append(f"- Car {p.refs['car']}: {p.car.get('make')} {p.car.get('model')} ({p.car.get('vehicle_type')}), ${p.car.get('daily_rate')}/day × {p.car.get('rental_days')} (capacity is an estimate)")
        out.append("- Lines: " + ", ".join(f"{k} ${v:,.2f}" for k, v in p.price_lines.items()))
    cond = {c.date: c for c in r.day_conditions}
    for d in r.days:
        c = cond.get(d.date)
        out.append(f"\n## {d.date} {' '.join(c.flags) if c else ''}")
        for it in d.items:
            f = facts.get(it.place_id, {})
            out.append(f"- {it.start}–{it.end} {'🍽 ' if it.kind == 'meal' else ''}{it.name or f.get('name')} "
                       f"({f.get('category')}; {it.mode} {it.travel_min} min)" + (f" — {it.weather_note}" if it.weather_note else ""))
    if r.tradeoffs or r.dropped:
        out.append("\n## What we gave up")
        out += [f"- {t}" for t in r.tradeoffs]
        out += [f"- {facts.get(x.place_id, {}).get('name', x.place_id)}: {x.reason}" for x in r.dropped]
    if r.check_report:
        out.append("\n## Checks: " + ", ".join(f"{c.name} {'✓' if c.passed else '✗'}" for c in r.check_report.checks))
    out.append("\nSources: OpenStreetMap (ODbL), Wikivoyage (CC BY-SA), Open-Meteo (CC BY 4.0), Inside Airbnb (CC BY 4.0), Kaggle flight/car datasets.")
    return "\n".join(out)
