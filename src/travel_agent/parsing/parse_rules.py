"""Keyword / regex parser for free-text trip requests (System A on eval v3). No LLM, deterministic.

Honest best effort: it recognises explicit, commonly phrased facts (airport codes and city names, month-day dates,
party size, dollar amounts, car yes/no, pace words, interest keywords with simple negation, nonstop / central /
flexible-date phrases, explicit clock times for naps / day start / day end / earliest flight, a few priority phrases).
Anything it recognises as a requirement but cannot map to a schema field goes to unparsed_requirements (so the plan
flags it); everything else is silently missed. Defaults it had to assume are listed in ParseResult.notes.
Written from general phrasing patterns and the 4 dev texts only; not tuned on the eval texts.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Optional

from ..config import CITIES
from ..models import FreeTextRequest
from . import ParseResult

AIRPORTS = {"ATL", "BOS", "CLT", "DEN", "DFW", "DTW", "EWR", "IAD", "JFK", "LAX", "LGA", "MIA", "OAK", "ORD", "PHL", "SFO"}
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "a couple of": 2, "a": 1, "an": 1}
PLACE_CODES = [  # (case-insensitive names, case-sensitive abbreviations, airport); destinations matched separately
    (r"\blos angeles\b|\bl\.a\.", r"\bLA\b", "LAX"), (r"\bboston\b", None, "BOS"), (r"\bmiami\b", None, "MIA"),
    (r"\bdallas\b|\bfort worth\b", None, "DFW"), (r"\bdenver\b", None, "DEN"), (r"\batlanta\b", None, "ATL"),
    (r"\bcharlotte\b", None, "CLT"), (r"\bdetroit\b", None, "DTW"), (r"\bwashington\b|\bd\.c\.|\bdulles\b", r"\bDC\b", "IAD"),
    (r"\bphiladelphia\b|\bphilly\b", None, "PHL"), (r"\bsan francisco\b", r"\bSF\b", "SFO"), (r"\boakland\b", None, "OAK"),
    (r"\bla ?guardia\b", None, "LGA"), (r"\bnewark\b", None, "EWR"), (r"\bkennedy\b", None, "JFK"), (r"\bo'?hare\b", None, "ORD"),
]
DEST = [(r"\bchicago\b|\bthe windy city\b", "Chicago"), (r"\bnew york\b|\bnyc\b|\bmanhattan\b|\bthe big apple\b", "New York")]
INTEREST_WORDS = {
    "food": r"food|eat|eating|restaurant|dining|foodie|cuisine|pizza|brunch",
    "culture": r"museum|museums|art|arts|galler\w*|culture|cultural|histor\w*",
    "attractions": r"sights|sightseeing|landmark\w*|attraction\w*|must-see\w*|famous spots|tourist spots|aquarium|zoo|observation deck",
    "nightlife": r"bars?|nightlife|clubs?|clubbing|cocktails?|pubs?|drinks|going out at night",
    "family": r"kids?|children|child|family|toddler|son|daughter",
    "nature": r"parks?|nature|outdoors|gardens?|lakefront|green spaces?|hiking",
    "shows": r"shows?|theat(?:er|re)s?|broadway|musicals?|concerts?|comedy|jazz|live music",
    "shopping": r"shopping|shops?|boutiques?|malls?",
    "extreme/adventure": r"adventure|thrill\w*|adrenaline",
}
NEG = r"(?:no|not|never|skip|avoid|without|hate|don'?t|do not|aren'?t|isn'?t|not into|not interested in|zero|none of)"
UNPARSED = [  # recognised but no schema field
    (r"vegetarian|vegan|kosher|halal|gluten", "dietary requirement"),
    (r"dinner (?:close|near|nearby|within walking)|(?:walk|walking) (?:back )?to (?:the )?(?:hotel|apartment|place) after dinner|"
     r"dinner .{0,30}(?:near|close to) (?:the |our )?(?:hotel|apartment|place|lodging)|"
     r"(?:food|dinners?|eat\w*|restaurants?) (?:near|close to) where we (?:sleep|stay)", "dinner near the lodging"),
    (r"limited mobility|bad knees?|can'?t walk (?:much|far|long)|hard (?:for \w+ )?to walk", "limited walking (no limit given)"),
    (r"not (?:a )?morning (?:people|person)|sleep in|late risers?", "late start (no time given)"),
    (r"\bquiet\b", "quiet lodging"),
    (r"\bdogs?\b|\bpets?\b", "travelling with a pet"),
]


def _hm(h: int, m: int = 0, ampm: Optional[str] = None) -> str:
    if ampm:
        ampm = ampm.lower().replace(".", "")
        if ampm.startswith("p") and h < 12:
            h += 12
        if ampm.startswith("a") and h == 12:
            h = 0
    return f"{h:02d}:{m:02d}"


TIME = r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?"


def _time(m, i: int = 1, pm_default: bool = False) -> str:
    h, mm, ap = int(m.group(i)), int(m.group(i + 1) or 0), m.group(i + 2)
    if not ap and pm_default and h < 12:
        ap = "pm"
    return _hm(h, mm, ap)


def _num(s: str) -> Optional[int]:
    s = s.lower().strip()
    return int(s) if s.isdigit() else NUM.get(s)


def _dates(text: str, year: int) -> tuple[Optional[dt.date], Optional[dt.date]]:
    t = text.lower()
    mon = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    pats = [
        rf"{mon}\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|to|through|until|till)\s*(?:{mon}\s+)?(\d{{1,2}})(?:st|nd|rd|th)?",
        rf"(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|to|through|until)\s*(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{mon}",
    ]
    m = re.search(pats[0], t)
    if m:
        m1, d1, m2, d2 = MONTHS[m.group(1)[:3]], int(m.group(2)), MONTHS[m.group(3)[:3]] if m.group(3) else None, int(m.group(4))
        m2 = m2 or (m1 if d2 >= d1 else m1 + 1)
        return dt.date(year, m1, d1), dt.date(year, m2, d2)
    m = re.search(pats[1], t)
    if m:
        mo = MONTHS[m.group(3)[:3]]
        return dt.date(year, mo, int(m.group(1))), dt.date(year, mo, int(m.group(2)))
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})\D+(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return dt.date(*map(int, m.group(1, 2, 3))), dt.date(*map(int, m.group(4, 5, 6)))
    md = list(re.finditer(rf"{mon}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", t))      # "leaving Thursday, August 25 ... home Sunday, August 28"
    if len(md) >= 2:
        a_, b_ = md[0], md[1]
        return dt.date(year, MONTHS[a_.group(1)[:3]], int(a_.group(2))), dt.date(year, MONTHS[b_.group(1)[:3]], int(b_.group(2)))
    m = re.search(rf"{mon}\s+(\d{{1,2}})(?:st|nd|rd|th)?", t)
    n = re.search(r"(\d+|two|three|four|five)\s+nights", t)
    if m and n:
        s = dt.date(year, MONTHS[m.group(1)[:3]], int(m.group(2)))
        return s, s + dt.timedelta(_num(n.group(1)) or 1)
    return None, None


def _travelers(t: str, notes: list[str]) -> int:
    me = re.search(r"\bme and (\d|two|three|four|five) (?:friends|others|colleagues|buddies|coworkers)\b", t)
    m = None if me else re.search(r"\b(\d|two|three|four|five|six)\s+(?:of us|people|persons|adults|travel+ers|friends|guys|girls)\b", t)
    if me:
        n = 1 + _num(me.group(1))
        m = me
    elif m:
        n = _num(m.group(1))
    elif re.search(r"family of (\d|three|four|five|six)", t):
        n = _num(re.search(r"family of (\d|three|four|five|six)", t).group(1))
    elif re.search(r"\b(solo|by myself|just me|alone|on my own)\b", t):
        n = 1
    elif re.search(r"\bme and my (wife|husband|partner|girlfriend|boyfriend|friend|mom|dad|mother|father|sister|brother)\b|\bcouple\b|\bthe two of us\b|\bboth of us\b", t):
        n = 2
    else:
        n = 2
        notes.append("travelers not found -> assumed 2")
    k = re.search(r"\b(?:and|plus|with)\s+(?:our|my)\s+(\d|two|three|four)\s+(?:kids|children|sons|daughters)\b", t)
    if k and not m and not re.search(r"family of", t):
        n += _num(k.group(1)) or 0
    elif re.search(r"\b(?:and|plus|with) (?:our|my) (?:kid|son|daughter|child|toddler)\b", t) and not m and not re.search(r"family of", t):
        n += 1
    return n


def _amounts(t: str) -> list[tuple[int, int]]:
    out = []
    for m in re.finditer(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k\b)?|\b(\d+(?:\.\d+)?)\s?k\b|\b(\d[\d,]{2,})\s*(?:dollars|usd|bucks)", t):
        raw = m.group(1) or m.group(3) or m.group(4)
        v = float(raw.replace(",", ""))
        if m.group(2) or m.group(3):
            v *= 1000
        out.append((int(round(v)), m.start()))
    m = re.search(r"\b(one|two|three|four|five) (?:grand|thousand)\b", t)
    if m:
        out.append((_num(m.group(1)) * 1000, m.start()))
    return out


def _interests(t: str) -> tuple[list[str], list[str]]:
    hits, avoid = [], []
    for k, pat in INTEREST_WORDS.items():
        for m in re.finditer(rf"\b(?:{pat})\b", t):
            pre = t[max(0, m.start() - 30):m.start()]
            neg = re.search(rf"\b{NEG}\b[^.,;!?]*$", pre)
            (avoid if neg else hits).append((m.start(), k))
    first_pos: dict[str, int] = {}
    for pos, k in sorted(hits):
        first_pos.setdefault(k, pos)
    av = sorted({k for _, k in avoid} - set(first_pos))
    ints = [k for k, _ in sorted(first_pos.items(), key=lambda x: x[1])][:4]
    return ints, av


def parse(ft: FreeTextRequest) -> ParseResult:
    text = ft.request_text
    t = text.lower()
    notes: list[str] = []
    f: dict[str, Any] = dict(request_id=ft.request_id, as_of=ft.as_of, request_text=text, free_text=text)
    # destination + origin
    dest = [(m.start(), c) for pat, c in DEST for m in re.finditer(pat, t)]
    cands = []      # (has 'from'-like prefix, position, airport)
    for ci, cs, code in PLACE_CODES:
        ms = list(re.finditer(ci, text, flags=re.I)) + (list(re.finditer(cs, text)) if cs else [])
        for m in ms:
            pre = t[max(0, m.start() - 25):m.start()]
            cands.append((bool(re.search(r"(from|out of|leaving|based in|live in|living in|home in)\s+(?:\w+\s+)?$", pre)), m.start(), code))
    for m in re.finditer(r"\b([A-Z]{3})\b", text):
        if m.group(1) in AIRPORTS:
            pre = t[max(0, m.start() - 25):m.start()]
            cands.append((bool(re.search(r"(from|out of|leaving)\s+(?:\w+\s+)?$", pre)), m.start(), m.group(1)))
    cands.sort(key=lambda x: (not x[0], x[1]))
    origin = cands[0][2] if cands else None
    cities = sorted({c for _, c in dest})
    if len(cities) == 1:
        f["city"] = cities[0]
    elif len(cities) == 2:   # e.g. "from New York to Chicago": the one after to/in/visit
        m = re.search(r"\b(?:to|in|visit|visiting|see)\s+(chicago|new york|nyc|manhattan)", t)
        f["city"] = "Chicago" if (m and m.group(1) == "chicago") else "New York"
    if origin is None and "city" in f and f["city"] == "Chicago" and re.search(r"\bnew york\b|\bnyc\b", t):
        origin = "LGA"
        notes.append("origin New York without an airport -> assumed LGA")
    if origin:
        f["origin"] = origin
    if origin and "city" in f and origin in CITIES[f["city"]]["airports"]:
        notes.append("origin equals a destination airport")
    # dates
    s, e = _dates(text, ft.as_of.year)
    if s:
        f["start_date"], f["end_date"] = s, e
    if re.search(r"give or take a day|\+/?-\s?1 day|a day (?:earlier|before) or (?:later|after)|flexible (?:by|with) (?:a|one) day|"
                 r"dates are (?:a bit )?flexible|could shift (?:by )?a day", t):
        f["depart_flex_days"] = f["return_flex_days"] = 1
    f["travelers"] = _travelers(t, notes)
    # budget
    am = _amounts(t)
    if am:
        vals = sorted({v for v, _ in am})
        f["budget_usd"] = vals[-1]
        if len(vals) >= 2 and re.search(r"ideally|prefer|rather|would love to (?:stay|keep)|hoping to", t):
            f["preferred_budget_usd"] = vals[0]
    else:
        notes.append("no budget amount found")
    # car / pace
    if re.search(r"\b(?:no|without a|don'?t need a|won'?t need a|skip the) (?:rental )?car\b|public transport|subway|\btransit\b", t):
        f["wants_car"] = False
    elif re.search(r"\brent(?:ing)? a car\b|\brental car\b|\bneed a car\b|\bwant a car\b|\bwith a car\b|\bwe'?ll drive\b", t):
        f["wants_car"] = True
    else:
        f["wants_car"] = False
        notes.append("car not mentioned -> no car")
    if re.search(r"relax\w*|slow pace|easy pace|laid[- ]back|not rushed|take it easy|chill|leisurely", t):
        f["pace"] = "relaxed"
    elif re.search(r"packed|as much as (?:we|i) can|see everything|action[- ]packed|busy schedule|cram", t):
        f["pace"] = "packed"
    ints, av = _interests(t)
    if not ints:
        ints = ["attractions"]
        notes.append("no interest keyword -> attractions")
    f["interests"], f["avoid"] = ints, [a for a in av if a not in ints]
    # lodging / flights soft prefs
    soft = []
    if re.search(r"(must|has to|have to|need to|needs to) be (?:central|downtown)|central (?:is a must|or nothing)", t):
        f["hotel_preference"] = "central"
    elif re.search(r"\bcentral\b|downtown|close to everything|in the (?:center|centre|middle) of|walkable area|the loop|midtown", t):
        soft.append("central")
    if re.search(r"non-?stop|direct flights?|no (?:connections|layovers?|stopovers?)", t):
        soft.append("nonstop")
    if re.search(r"avoid (?:the )?rain|dry (?:days|weather)|(?:don'?t|do not) want rain|hate rain", t):
        soft.append("dry_days")
    if f.get("depart_flex_days") and "dry_days" in soft:
        soft.append("exact_dates") if re.search(r"ideally (?:on )?(?:those|these|the) dates|prefer (?:the|those) dates", t) else None
    if re.search(r"land (?:early|by)|arrive early|(?:don'?t|not) (?:want to )?lose a day|make the most of (?:the|each) day", t):
        soft.append("long_days")
    if f.get("preferred_budget_usd"):
        soft.append("under_preferred_budget")
    f["soft_prefs"] = soft
    # priorities
    w = {}
    if re.search(r"location (?:matters|is) more (?:important )?than (?:the )?price|(?:happy|willing|ok|fine) to pay (?:a bit |a little )?more (?:for|to be) (?:a )?(?:central|good location|location)|location (?:over|before) price", t):
        w["central"] = 2.0
        if "central" not in soft and f.get("hotel_preference") != "central":
            soft.append("central")
    if re.search(r"nonstop (?:matters|is) more|direct flights? (?:matter|is|are) more", t):
        w["nonstop"] = 2.0
    if re.search(r"price (?:matters|is) (?:the )?most|cheapest (?:option|possible)|as cheap as possible", t):
        w["price"] = 2.0
    f["priority_weights"] = w
    # times
    blocked = []
    for m in re.finditer(rf"(nap|rest|prayer|pray|siesta|break)\w*[^.;]{{0,30}}?(?:from|between)\s+{TIME}\s*(?:-|–|to|and)\s*{TIME}", t):
        blocked.append(dict(start=_time(m, 2, True), end=_time(m, 5, True), label=m.group(1)))
    for m in re.finditer(rf"keep\s+{TIME}\s*(?:-|–|to)\s*{TIME}\s+(?:free|open|empty)", t):
        blocked.append(dict(start=_time(m, 1, True), end=_time(m, 4, True), label="kept free"))
    if not blocked and re.search(r"\bnaps?\b[^.;]{0,25}after lunch|after lunch[^.;]{0,25}\bnaps?\b", t):
        blocked.append(dict(start="13:00", end="15:00", label="nap (after lunch, assumed 13:00-15:00)"))
    f["daily_blocked_windows"] = blocked
    m = re.search(rf"(?:nothing|no plans|don'?t start|not start|start no earlier) (?:before|than|earlier than)\s+{TIME}", t)
    if m:
        f["day_start"] = _time(m)
    m = re.search(rf"(?:back (?:at the (?:hotel|apartment) )?by|done by|in bed by|finish by|wrap up by)\s+{TIME}", t)
    if m:
        f["day_end"] = _time(m, 1, True)
    m = re.search(rf"no (?:flights?|departures?) (?:before|earlier than)\s+{TIME}|(?:flights?|departures?) (?:not|no) (?:before|earlier than)\s+{TIME}", t)
    if m:
        g = 1 if m.group(1) else 4
        f["no_early_flight_before"] = _time(m, g)
    elif re.search(r"no (?:early|early-morning|early morning|red-?eye) (?:flights?|departures?)", t):
        f["no_early_flight_before"] = "09:00"
        notes.append("'no early flights' -> assumed 09:00")
    m = re.search(r"(?:walk|walking) (?:more than|over|longer than)\s+(\d+)\s*(?:min|minutes)", t)
    if m:
        f["max_walk_minutes"] = int(m.group(1))
    if re.search(r"wheelchair|step-free|accessible|accessibility", t):
        f["accessibility"] = True
    f["unparsed_requirements"] = [label for pat, label in UNPARSED if re.search(pat, t)]
    missing = [k for k in ("city", "origin", "start_date", "end_date", "budget_usd") if k not in f]
    if missing:
        return ParseResult("keyword", None, notes, error="could not find " + ", ".join(missing))
    return ParseResult("keyword", f, notes)
