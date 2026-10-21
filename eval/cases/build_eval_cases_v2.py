#!/usr/bin/env python3
"""Build eval set v2 (Travel Agent, team 8, BIU DS23): rebuilt conflicting cases (groups B, C, D) that each require
a REAL, verified trade-off. Groups A (easy) and E (infeasible) and the non-conflict dev cases are copied from v1
(eval_cases.json, kept unchanged for history); New York oracle_places is now filled from data/places/nyc_places.csv.

    python eval/cases/build_eval_cases_v2.py      -> eval/cases/eval_cases_v2.json / .csv + build log

Everything is computed from local files with the same code the systems use (travel_agent.data_access catalog,
travel_agent.prefs, weather fixtures in data/weather - Open-Meteo, CC BY 4.0). Deterministic (seed fixed).

True-conflict test (per candidate case, after the budget is fixed):
  enumerate ALL packages (outbound x return x lodging [x car], every date pair allowed by the flex fields) that pass
  the hard constraints (seats, same-day arrival, capacity, availability, min/max nights, <= 12 km, car at the arrival
  airport, budget); evaluate the soft preferences of each package (prefs.evaluate). TRUE CONFLICT iff
    (i)  no feasible package satisfies every soft preference, and
    (ii) the Pareto front of the feasible packages' sacrificed-preference sets has >= 2 members (i.e. >= 2
         Pareto-optimal packages that sacrifice DIFFERENT preferences).
  The acceptable sacrifices of the case are exactly the Pareto-front sets. Candidates that fail are discarded and
  the next (route, window) is tried. Route/window order: densest first (number of distinct feasible packages).
"""
from __future__ import annotations

import bisect, csv, datetime as dt, hashlib, json, math, os, random, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'src'))
from travel_agent import config as C            # noqa: E402
from travel_agent import prefs as P             # noqa: E402
from travel_agent.data_access import get_catalog  # noqa: E402
from travel_agent.tools import _fixture_day, classify  # noqa: E402

SEED = 20261030
V1 = os.path.join(HERE, 'eval_cases.json')
OUT_JSON = os.path.join(HERE, 'eval_cases_v2.json')
OUT_CSV = os.path.join(HERE, 'eval_cases_v2.csv')
OUT_LOG = os.path.join(HERE, 'v2', 'build_log_v2.json')
AS_OF_FAR, AS_OF_NEAR = 30, 2
MIN_FEASIBLE = 20            # "many options": a conflicting case must have >= 20 feasible packages
MAX_ORIGIN_USE = 4           # per city among the new cases
MAX_MONTH_USE = 8            # per city and month among the new cases
SLOTS = {'relaxed': 2, 'normal': 3, 'packed': 5}

CAT = get_catalog()
DATES = CAT.dates
DI = CAT.date_index


def s2d(s): return dt.date.fromisoformat(s)
def d2s(d): return d.isoformat()
def sh(s, k): return d2s(s2d(s) + dt.timedelta(k))
def ceil10(x): return int(math.ceil(x / 10.0) * 10)
def floor10(x): return int(math.floor(x / 10.0) * 10)


# ---------------------------------------------------------------- weather (fixtures, same as the tool)
_WX: dict = {}
def wx_flags(city, date):
    k = (city, date)
    if k not in _WX:
        rec = _fixture_day(city, date)
        if rec is None:
            _WX[k] = None
        else:
            v = rec['values']
            _WX[k] = classify(v.get('precipitation_sum'), v.get('precipitation_hours'), v.get('apparent_temperature_max'), v.get('wind_gusts_10m_max'))
    return _WX[k]


def rain_map(city, dates, as_of):
    m = {}
    for d in dates:
        lead = (s2d(d) - s2d(as_of)).days
        fl = wx_flags(city, d) if lead <= C.HORIZON_DAYS else None
        m[d] = None if fl is None else ('RAIN' in fl)
    return m


# ---------------------------------------------------------------- catalog helpers (mirror tools.py hard filters)
def flights_out(origin, airports, date, T):
    return [f for a in airports for f in CAT.flights_on(origin, a, date) if f['seats'] > 0 and f['seats'] >= T and f['arrivalDate'] == date]


def flights_back(origin, airports, date, T):
    return [f for a in airports for f in CAT.flights_on(a, origin, date) if f['seats'] > 0 and f['seats'] >= T]


_STAY_CACHE: dict = {}
def stays_ok(city, ci, co, T, central_hard=False):
    key = (city, ci, co, T, central_hard)
    if key in _STAY_CACHE: return _STAY_CACHE[key]
    n = (s2d(co) - s2d(ci)).days; out = []
    if ci in DI and n > 0:
        i0 = DI[ci]
        for k in CAT.city_stay_keys(city):
            s = CAT.stays[k]
            if s.get('capacity') is None or s['capacity'] < T: continue
            av, mn, mx = CAT.decode(k)
            if not (mn[i0] > 0 and mx[i0] > 0 and mn[i0] <= n <= mx[i0]): continue
            if not all((sh(ci, j) in DI and av[DI[sh(ci, j)]] == 2) for j in range(n)): continue
            km = CAT.stay_km_to_center(city, k)
            if km > C.MAX_STAY_KM or (central_hard and km > C.CENTRAL_RADIUS_KM[city]): continue
            out.append((k, km, s['price']))
    _STAY_CACHE[key] = out
    return out


def cars_ok(airport, start, end, T):
    out = []
    for cid in CAT.cars_by_airport.get(airport, []):
        c = CAT.cars[cid]
        if any(not (b[1] < start or b[0] > end) for b in c.get('blackouts', [])): continue
        if c['capacityEstimate'] < T: continue
        out.append(c)
    return out


def date_pairs(start, end, fd, fr):
    """Mirror of TripRequest.date_pairs (each end +-flex, trip length changes by <= 1 night)."""
    pairs = [(start, end)]
    n0 = (s2d(end) - s2d(start)).days
    for a in range(-fd, fd + 1):
        for b in range(-fr, fr + 1):
            s, e = sh(start, a), sh(end, b)
            if (s, e) not in pairs and s >= DATES[0] and e <= DATES[-1] and (s2d(e) - s2d(s)).days >= 1 and \
                    abs((s2d(e) - s2d(s)).days - n0) <= 1:
                pairs.append((s, e))
    return pairs


# ---------------------------------------------------------------- package enumeration
def enumerate_packages(case):
    """All hard-feasible packages ignoring the budget. Each base package = (out, back, stay[, airport]) with the
    cheapest car; car variants are kept as a sorted cost list for counting. Returns list of dicts."""
    city, T = case['city'], case['travelers']; airports = C.CITIES[city]['airports']
    fd, fr = case.get('depart_flex_days', 0), case.get('return_flex_days', 0)
    pkgs = []
    for s, e in date_pairs(case['start_date'], case['end_date'], fd, fr):
        n = (s2d(e) - s2d(s)).days
        O, B = flights_out(case['origin'], airports, s, T), flights_back(case['origin'], airports, e, T)
        if not O or not B: continue
        St = stays_ok(city, s, e, T, case.get('hotel_preference') == 'central')
        if not St: continue
        groups = []
        if case['wants_car']:
            for a in airports:
                Oa, Ba = [o for o in O if o['destination'] == a], [b for b in B if b['origin'] == a]
                if not Oa or not Ba: continue
                cs = cars_ok(a, s, e, T)
                if not cs: continue
                costs = sorted(c['dailyRate'] * (n + 1) for c in cs)
                cheapest = min(cs, key=lambda c: (c['dailyRate'], c['id']))
                groups.append((Oa, Ba, costs, cheapest))
        else:
            groups.append((O, B, [0.0], None))
        for Oa, Ba, costs, car in groups:
            for o in Oa:
                for b in Ba:
                    for k, km, price in St:
                        base = (o['fare'] + b['fare']) * T + price * n
                        pkgs.append(dict(start=s, end=e, nights=n, o=o, b=b, stay=k, km=km, price=price, base=base,
                                         car_costs=costs, car=car, total=round(base + costs[0], 2)))
    return pkgs


def vectors(case, pkgs):
    rm = rain_map(case['city'], sorted({d for p in pkgs for d in [sh(p['start'], i) for i in range(p['nights'] + 1)]}), case['as_of'])
    for p in pkgs:
        vec = P.evaluate(case['soft_prefs'], city=case['city'], req_start=case['start_date'], req_end=case['end_date'],
                         flight_out=p['o'], flight_back=p['b'], stay_km=p['km'], total=p['total'],
                         preferred_budget=case.get('preferred_budget_usd'), rain_by_date=rm)
        p['vec'] = vec
        p['sac'] = P.sacrificed(vec)
        p['unknown'] = [k for k, v in vec.items() if v is None]
    return pkgs


def n_within(pkgs, budget):
    n = 0
    for p in pkgs:
        n += bisect.bisect_right(p['car_costs'], budget - p['base'] + 1e-9)
    return n


def pkg_summary(p, T):
    o, b = p['o'], p['b']
    return dict(total=p['total'], start_date=p['start'], end_date=p['end'], nights=p['nights'],
                flight_out=o['ref'], out_airport=o['destination'], out_nonstop=o['nonstop'], out_arrival_local=o['arrival'][11:16],
                out_fare=o['fare'], flight_back=b['ref'], back_airport=b['origin'], back_nonstop=b['nonstop'],
                back_departure_local=b['departure'][11:16], back_fare=b['fare'], stay=p['stay'], stay_km_to_center=round(p['km'], 2),
                stay_price=p['price'], car=('C' + p['car']['id']) if p['car'] else None,
                car_daily_rate=p['car']['dailyRate'] if p['car'] else None)


def true_conflict_test(case, pkgs):
    """Returns (passed, details). pkgs must carry vectors; the case budget is applied here."""
    budget = case['budget_usd']
    feas = [p for p in pkgs if p['total'] <= budget + 1e-9]
    nf = n_within(feas, budget)
    det = dict(n_feasible_packages=nf, n_feasible_base_packages=len(feas))
    if not feas:
        return False, dict(det, reason='no feasible package')
    if any(p['unknown'] for p in feas):
        return False, dict(det, reason='a soft preference cannot be evaluated (no forecast?)')
    sacs = Counter(p['sac'] for p in feas)
    det['profiles'] = {('none' if not k else '+'.join(k)): v for k, v in sorted(sacs.items(), key=lambda x: (len(x[0]), x[0]))}
    if () in sacs:
        return False, dict(det, reason='(i) failed: a feasible package satisfies every soft preference')
    front = P.pareto_front(sacs)
    det['pareto_front'] = [list(f) for f in front]
    if len(front) < 2:
        return False, dict(det, reason='(ii) failed: only one Pareto-optimal sacrifice profile (%s)' % '+'.join(front[0]))
    if nf < MIN_FEASIBLE:
        return False, dict(det, reason='fewer than %d feasible packages' % MIN_FEASIBLE)
    opts = []
    for f in front:
        best = min((p for p in feas if p['sac'] == f), key=lambda p: (p['total'], p['km'], p['o']['ref'], p['b']['ref'], p['stay']))
        opts.append(dict(sacrifices=list(f), satisfies=[k for k in case['soft_prefs'] if k not in f],
                         n_packages=n_within([p for p in feas if p['sac'] == f], budget), cheapest=pkg_summary(best, case['travelers'])))
    cheapest_all = min(feas, key=lambda p: (p['total'], p['km'], p['o']['ref'], p['b']['ref'], p['stay']))
    det.update(pareto_options=opts, acceptable_sacrifices=[list(f) for f in front],
               cheapest_feasible=dict(sacrifices=list(cheapest_all['sac']), total=cheapest_all['total'],
                                      on_pareto_front=cheapest_all['sac'] in front))
    return True, det


# ---------------------------------------------------------------- budget design
def min_cost_by_profile(pkgs):
    m = {}
    for p in pkgs:
        if p['unknown']: continue
        if p['sac'] not in m or p['total'] < m[p['sac']]: m[p['sac']] = p['total']
    return m


def design_budget(case, pkgs, kind):
    """Pick the hard budget (and the preferred budget for pref_budget cases) so that >= 2 single-sacrifice profiles
    are affordable while the all-satisfied profile is not (budget conflicts), or comfortably above everything
    (weather / preferred-budget conflicts, where the conflict is not created by the hard budget)."""
    prefs = case['soft_prefs']
    if kind == 'pref_budget':
        # preferred budget between the cheapest package overall and the cheapest package satisfying the other prefs
        others = [k for k in prefs if k != 'under_preferred_budget']
        case['preferred_budget_usd'] = 10 ** 9
        vectors(case, pkgs)
        c_all = min((p['total'] for p in pkgs), default=None)
        c_oth = min((p['total'] for p in pkgs if not (set(p['sac']) & set(others))), default=None)
        if c_all is None or c_oth is None or c_oth < 1.08 * c_all:
            return None
        case['preferred_budget_usd'] = floor10((c_all + c_oth) / 2)
        if not (c_all <= case['preferred_budget_usd'] < c_oth):
            return None
        case['budget_usd'] = ceil10(c_oth * 1.25)
        vectors(case, pkgs)
        return case['budget_usd']
    vectors(case, pkgs)
    m = min_cost_by_profile(pkgs)
    if kind == 'weather':
        front = P.pareto_front(m)
        if () in m or len(front) < 2:
            return None
        case['budget_usd'] = ceil10(max(m[f] for f in front) * 1.3)
        return case['budget_usd']
    M = m.get((), float('inf'))
    singles = sorted(v for k, v in m.items() if len(k) == 1 and v < M)
    if len(singles) < 2:
        return None
    c2 = singles[1]
    # the largest round budget that still cannot buy the all-satisfied package (most options, real conflict)
    b = (int(math.ceil(M / 10.0)) - 1) * 10 if M < float('inf') else ceil10(c2 * 1.15)
    if b < c2 or b >= M: return None
    case['budget_usd'] = b
    return b


# ---------------------------------------------------------------- places oracle (both cities now)
PLACES = {}
for city, cfg in C.CITIES.items():
    p = os.path.join(ROOT, 'data', 'places', '%s_places.csv' % cfg['key'])
    if os.path.exists(p):
        PLACES[city] = list(csv.DictReader(open(p, encoding='utf-8')))


def places_oracle(case):
    city = case['city']
    if city not in PLACES:
        return dict(status='TO_BE_FILLED', reason='%s_places.csv not available' % C.CITIES[city]['key'])
    rows = PLACES[city]; avoid = set(case['avoid'])
    def tags(r): return set(t for t in r['tags'].split(';') if t)
    usable = [r for r in rows if not (tags(r) & avoid)]
    per = {}
    for t in case['interests']:
        rs = [r for r in usable if t in tags(r)]
        per[t] = dict(total=len(rs), indoor_true=sum(r['indoor'] == 'true' for r in rs), outdoor_or_unknown=sum(r['indoor'] != 'true' for r in rs),
                      notable=sum(1 for r in rs if r.get('in_wikivoyage') == 'true' and r.get('wikidata')))
    days = [sh(case['start_date'], i) for i in range((s2d(case['end_date']) - s2d(case['start_date'])).days + 1)]
    rain = [d for d in days if case['weather_fixture_needed'] and 'RAIN' in (wx_flags(city, d) or [])]
    dry = [d for d in days if d not in rain]
    slots = max(0, len(days) - 2) * SLOTS[case['pace']] + 2
    need = math.ceil(C.COVERAGE_MIN * len(case['interests']))
    coverable = [t for t in case['interests'] if per[t]['total'] > 0 and (per[t]['indoor_true'] > 0 or dry)]
    ok = slots >= need and len(coverable) >= need
    return dict(status='PASS' if ok else 'FAIL', activity_slots_estimate=slots, interests_needed=need, coverable_interests=coverable,
                per_interest=per, rain_days=rain, dry_days=len(dry),
                note='necessary-condition check (slots + tag/indoor availability) for the requested dates; ratings not used')


# ---------------------------------------------------------------- templates (v2 conflicting + dev conflicting)
# (id, split, group, city, T, nights, car, pace, interests, avoid, soft_prefs, flex, kind, conflict_type)
CH, NY = 'Chicago', 'New York'
TPL = [
    ('B01', 'eval', 'B', CH, 2, 3, False, 'relaxed', ['culture', 'food'], [], ['central', 'nonstop'], 0, 'budget', 'budget: central lodging vs nonstop flights'),
    ('B02', 'eval', 'B', CH, 2, 3, False, 'normal', ['food', 'nightlife'], [], ['central', 'nonstop'], 1, 'budget', 'budget: central lodging vs nonstop flights (dates flexible +-1, no date preference)'),
    ('B03', 'eval', 'B', CH, 2, 3, False, 'normal', ['culture', 'attractions', 'food'], [], ['nonstop', 'long_days'], 0, 'budget', 'budget: nonstop vs flight times'),
    ('B04', 'eval', 'B', CH, 2, 2, False, 'packed', ['attractions', 'shows', 'food'], [], ['central', 'under_preferred_budget'], 0, 'pref_budget', 'central lodging vs preferred (soft) budget'),
    ('B05', 'eval', 'B', CH, 1, 4, False, 'relaxed', ['culture', 'nature'], [], ['central', 'exact_dates'], 1, 'budget', 'budget: central lodging vs exact dates (date flex +-1)'),
    ('B06', 'eval', 'B', CH, 3, 3, False, 'normal', ['family', 'attractions'], ['nightlife'], ['central', 'nonstop', 'long_days'], 0, 'budget', 'budget: central vs nonstop vs flight times (3-way)'),
    ('B07', 'eval', 'B', NY, 2, 3, False, 'relaxed', ['culture', 'food'], [], ['central', 'nonstop'], 0, 'budget', 'budget: central lodging vs nonstop flights'),
    ('B08', 'eval', 'B', NY, 1, 3, False, 'normal', ['shows', 'nightlife', 'food'], [], ['central', 'long_days'], 0, 'budget', 'budget: central lodging vs long arrival/departure days'),
    ('B09', 'eval', 'B', NY, 2, 3, False, 'normal', ['attractions', 'culture'], [], ['nonstop', 'long_days'], 0, 'budget', 'budget: nonstop vs flight times'),
    ('B10', 'eval', 'B', NY, 2, 2, False, 'packed', ['culture', 'shopping', 'food'], [], ['central', 'under_preferred_budget'], 0, 'pref_budget', 'central lodging vs preferred (soft) budget'),
    ('B11', 'eval', 'B', NY, 2, 4, False, 'relaxed', ['nature', 'culture'], [], ['central', 'exact_dates'], 1, 'budget', 'budget: central lodging vs exact dates (date flex +-1)'),
    ('B12', 'eval', 'B', NY, 3, 3, False, 'normal', ['family', 'attractions'], ['nightlife'], ['central', 'nonstop', 'long_days'], 0, 'budget', 'budget: central vs nonstop vs flight times (3-way)'),
    ('C01', 'eval', 'C', CH, 4, 3, True, 'normal', ['family', 'attractions'], ['nightlife'], ['central', 'nonstop'], 0, 'budget', 'car (4 travelers, estimated capacity) + budget: central vs nonstop'),
    ('C02', 'eval', 'C', CH, 3, 4, True, 'normal', ['culture', 'food'], [], ['central', 'long_days'], 0, 'budget', 'car + budget: central vs flight times'),
    ('C03', 'eval', 'C', CH, 2, 3, True, 'relaxed', ['nature', 'food'], [], ['central', 'under_preferred_budget'], 0, 'pref_budget', 'car cost: central lodging vs preferred (soft) budget'),
    ('C04', 'eval', 'C', NY, 4, 3, True, 'normal', ['attractions', 'family'], ['nightlife'], ['central', 'nonstop'], 0, 'budget', 'car (4 travelers, estimated capacity) + budget: central vs nonstop'),
    ('C05', 'eval', 'C', NY, 3, 3, True, 'relaxed', ['food', 'culture'], [], ['nonstop', 'long_days'], 0, 'budget', 'car + budget (same-airport pick-up): nonstop vs flight times'),
    ('C06', 'eval', 'C', NY, 2, 3, True, 'normal', ['nature', 'attractions'], [], ['central', 'under_preferred_budget'], 0, 'pref_budget', 'car cost: central lodging vs preferred (soft) budget'),
    ('D01', 'eval', 'D', CH, 2, 3, False, 'normal', ['nature', 'attractions'], [], ['dry_days', 'exact_dates'], 1, 'weather', 'weather: rain on the requested dates vs shifting the trip by a day'),
    ('D02', 'eval', 'D', CH, 1, 3, False, 'relaxed', ['nature', 'food'], [], ['dry_days', 'exact_dates', 'nonstop'], 1, 'weather', 'weather + flights: dry days vs exact dates vs nonstop'),
    ('D03', 'eval', 'D', CH, 2, 3, True, 'normal', ['nature', 'family'], [], ['dry_days', 'exact_dates'], 1, 'weather', 'weather (car): rain on the requested dates vs shifting the trip'),
    ('D04', 'eval', 'D', NY, 2, 3, False, 'normal', ['nature', 'attractions'], [], ['dry_days', 'exact_dates'], 1, 'weather', 'weather: rain on the requested dates vs shifting the trip by a day'),
    ('D05', 'eval', 'D', NY, 1, 3, False, 'relaxed', ['nature', 'food'], [], ['dry_days', 'exact_dates', 'central'], 1, 'weather', 'weather + lodging: dry days vs exact dates vs central'),
    ('D06', 'eval', 'D', NY, 2, 3, True, 'normal', ['nature', 'family'], [], ['dry_days', 'exact_dates'], 1, 'weather', 'weather (car): rain on the requested dates vs shifting the trip'),
    ('V02', 'dev', 'B', CH, 1, 3, False, 'relaxed', ['food', 'culture'], [], ['central', 'nonstop'], 1, 'budget', 'budget: central lodging vs nonstop flights'),
    ('V03', 'dev', 'C', CH, 3, 3, True, 'normal', ['family', 'attractions'], [], ['central', 'long_days'], 0, 'budget', 'car + budget: central vs flight times'),
    ('V04', 'dev', 'D', CH, 2, 3, False, 'normal', ['nature', 'attractions'], [], ['dry_days', 'exact_dates'], 1, 'weather', 'weather: rain on the requested dates vs shifting the trip'),
    ('V07', 'dev', 'B', NY, 2, 3, False, 'relaxed', ['food', 'culture'], [], ['central', 'nonstop'], 0, 'budget', 'budget: central lodging vs nonstop flights'),
    ('V08', 'dev', 'D', NY, 2, 3, False, 'normal', ['nature', 'food'], [], ['dry_days', 'exact_dates'], 1, 'weather', 'weather: rain on the requested dates vs shifting the trip'),
]
FALLBACK_PREFS = [['central', 'nonstop'], ['central', 'long_days'], ['nonstop', 'long_days']]

FREE_TEXT = {'culture': 'museums and galleries', 'food': 'local food', 'attractions': 'the classic sights', 'nightlife': 'bars in the evening',
             'family': 'kid-friendly places', 'nature': 'parks and the waterfront', 'shows': 'a show or concert', 'shopping': 'some shopping',
             'extreme/adventure': 'something active'}
AVOID_TEXT = {'nightlife': 'no bars', 'shopping': 'no malls'}
PREF_TEXT = {'central': 'we would love to stay central', 'nonstop': 'nonstop flights if possible',
             'exact_dates': 'we could move the trip by a day but prefer our dates', 'dry_days': 'we hope for dry weather for the outdoor parts',
             'long_days': 'ideally land by early afternoon and fly back late', 'under_preferred_budget': 'ideally spend under ${pb}'}


# ---------------------------------------------------------------- window ranking (densest first)
_DENS: dict = {}
def window_density(city, origin, start, nights, T, flex):
    """#distinct (out x back x lodging) combos over the allowed date pairs (no budget, no car)."""
    k = (city, origin, start, nights, T, flex)
    if k in _DENS: return _DENS[k]
    end = sh(start, nights); airports = C.CITIES[city]['airports']; n = 0
    if end in DI:
        for s, e in date_pairs(start, end, flex, flex):
            no = len(flights_out(origin, airports, s, T))
            if not no: continue
            nb = len(flights_back(origin, airports, e, T))
            if not nb: continue
            n += no * nb * len(stays_ok(city, s, e, T))
    _DENS[k] = n
    return n


def ranked_windows(city, nights, T, flex, rng):
    origins = [o for o in CAT.origins if o not in C.CITIES[city]['airports']]
    ws = []
    for o in origins:
        for s in DATES:
            d = window_density(city, o, s, nights, T, flex)
            if d > 0: ws.append((d, o, s))
    rng.shuffle(ws)                       # ties broken by the fixed seed
    ws.sort(key=lambda x: -x[0])
    return ws


def main():
    rng = random.Random(SEED)
    v1 = json.load(open(V1))
    v1_by = {c['id']: c for c in v1['cases']}
    keep_ids = [c['id'] for c in v1['cases'] if c['group'] in 'AE' or c['id'] in ('V01', 'V05', 'V06')]
    used = set((c['city'], c['start_date']) for c in v1['cases'] if c['id'] in keep_ids)
    origin_use, month_use = Counter(), Counter()
    log = dict(candidates_tested=0, passed=0, failed=0, fail_reasons=Counter(), no_budget_design=0, per_case={})
    new_cases = {}
    for (cid, split, grp, city, T, nights, car, pace, interests, avoid, prefs, flex, kind, ctype) in TPL:
        chosen = None; tried = 0
        kinds = [(prefs, kind)] + [(f, 'budget') for f in FALLBACK_PREFS if f != prefs and kind != 'weather']
        for pr, kind in kinds:
            for dens, o, s in ranked_windows(city, nights, T, flex, rng):
                e = sh(s, nights)
                if (city, s) in used or (split == 'eval' and origin_use[(city, o)] >= MAX_ORIGIN_USE) or month_use[(city, s[:7])] >= MAX_MONTH_USE: continue
                if any(c == city and abs((s2d(x) - s2d(s)).days) <= 1 for c, x in used): continue
                near = kind == 'weather'
                case = dict(id=cid, split=split, group=grp, city=city, origin=o, start_date=s, end_date=e, travelers=T, wants_car=car,
                            pace=pace, interests=interests, avoid=avoid, hotel_preference='any', soft_prefs=list(pr),
                            depart_flex_days=flex, return_flex_days=flex,
                            as_of=sh(s, -(AS_OF_NEAR if near else AS_OF_FAR)))
                if near:   # the requested dates must contain a rain day (not the departure day) - cheap pre-filter
                    rm = rain_map(city, [sh(s, i) for i in range(nights)], case['as_of'])
                    if not any(rm.values()): continue
                pkgs = enumerate_packages(case)
                if not pkgs: continue
                if design_budget(case, pkgs, kind) is None:
                    log['no_budget_design'] += 1
                    continue
                tried += 1; log['candidates_tested'] += 1
                ok, det = true_conflict_test(case, pkgs)
                if not ok:
                    log['failed'] += 1; log['fail_reasons'][det['reason'].split(':')[0]] += 1
                    continue
                log['passed'] += 1
                case['_density'] = dens
                chosen = (case, det, pkgs); break
            if chosen: break
        if not chosen:
            print('!! no true-conflict window for', cid, file=sys.stderr); continue
        case, det, pkgs = chosen
        if case['soft_prefs'] != prefs:   # template preferences had no true-conflict window -> fallback preferences
            names = {'central': 'central lodging', 'nonstop': 'nonstop flights', 'long_days': 'long arrival/departure days'}
            ctype = ('car + ' if car else '') + 'budget: ' + ' vs '.join(names.get(x, x) for x in case['soft_prefs']) + \
                (' (dates flexible +-1, no date preference)' if flex else '') + ' [fallback from %s]' % '+'.join(prefs)
        used.add((city, case['start_date'])); origin_use[(city, case['origin'])] += 1; month_use[(city, case['start_date'][:7])] += 1
        log['per_case'][cid] = dict(candidates_tested=tried, window_density=case['_density'], prefs_used=case['soft_prefs'])
        new_cases[cid] = finish_case(case, det, pkgs, ctype)
    # assemble in v1 order: A, B, C, D, E, dev
    out = []
    for c in v1['cases']:
        if c['id'] in keep_ids:
            out.append(upgrade_v1(c))
        elif c['id'] in new_cases:
            out.append(new_cases[c['id']])
    meta = dict(v1['meta'], version='v2', built_with='build_eval_cases_v2.py', seed=SEED, v1_file='eval_cases.json (frozen v1, unchanged)',
                v1_sha256=hashlib.sha256(open(V1, 'rb').read()).hexdigest(),
                weather_source='Open-Meteo Historical Forecast API, CC BY 4.0 (data/weather fixtures, retrieved 2026-10-21)',
                places_available={c: (c in PLACES) for c in C.CITIES}, soft_prefs=P.SOFT_PREFS,
                long_days=dict(arrive_by=P.LONG_DAYS_ARRIVE_BY, depart_from=P.LONG_DAYS_DEPART_FROM),
                true_conflict_test='(i) no feasible package satisfies all soft prefs; (ii) >= 2 Pareto-optimal sacrifice profiles; '
                                   'feasible = all hard constraints incl. budget; n_feasible >= %d' % MIN_FEASIBLE,
                window_order='densest (origin, start) first by #distinct out x back x lodging combos (incl. flex pairs)',
                build_summary=dict(candidates_tested=log['candidates_tested'], passed=log['passed'], failed=log['failed'],
                                   fail_reasons=dict(log['fail_reasons']), windows_without_budget_design=log['no_budget_design']))
    json.dump(dict(meta=meta, cases=out), open(OUT_JSON, 'w'), ensure_ascii=False, indent=1)
    log['fail_reasons'] = dict(log['fail_reasons'])
    log['v1_conflicting_retest'] = retest_v1(v1['cases'])
    os.makedirs(os.path.dirname(OUT_LOG), exist_ok=True)
    json.dump(log, open(OUT_LOG, 'w'), indent=1)
    write_csv(out)
    cnt = Counter((c['split'], c['group'], c['city']) for c in out)
    for k in sorted(cnt): print(k, cnt[k])
    print('candidates tested %d, passed %d, failed %d %s; windows without a budget design %d' % (
        log['candidates_tested'], log['passed'], log['failed'], log['fail_reasons'], log['no_budget_design']))
    print('v1 conflicting cases re-tested:', {k: v for k, v in log['v1_conflicting_retest'].items() if k != 'per_case'})
    for c in out:
        if c.get('true_conflict'):
            tc = c['true_conflict']
            print(c['id'], c['city'][:3], c['origin'], c['start_date'], c['end_date'], 'T=%d' % c['travelers'], 'car' if c['wants_car'] else '-',
                  c['soft_prefs'], '$%d' % c['budget_usd'], 'pref$%s' % c.get('preferred_budget_usd'), 'n_feasible=%d' % tc['n_feasible_packages'],
                  'front=%s' % tc['acceptable_sacrifices'], 'cheapest_on_front=%s' % tc['cheapest_feasible']['on_pareto_front'],
                  c['oracle_places']['status'])


def finish_case(case, det, pkgs, ctype):
    city = case['city']
    days = [sh(case['start_date'], i) for i in range((s2d(case['end_date']) - s2d(case['start_date'])).days + 1)]
    all_days = [sh(case['start_date'], i) for i in range(-case['depart_flex_days'], len(days) + case['return_flex_days'])]
    leads = {d: (s2d(d) - s2d(case['as_of'])).days for d in all_days}
    case['weather_fixture_needed'] = any(l <= C.HORIZON_DAYS for l in leads.values())
    case['weather_fixture_files'] = ['data/weather/%s_2022_season.json' % C.CITIES[city]['key']] if case['weather_fixture_needed'] else []
    case['weather_expected'] = {d: ((wx_flags(city, d) or ['NONE']) or ['NONE']) if leads[d] <= C.HORIZON_DAYS else ['OUT_OF_HORIZON'] for d in all_days}
    txt = 'I would like ' + ', '.join(FREE_TEXT[t] for t in case['interests'])
    if case['avoid']: txt += '; ' + ', '.join(AVOID_TEXT.get(a, 'no ' + a) for a in case['avoid'])
    if case['pace'] == 'relaxed': txt += '; no packed days'
    txt += '; ' + '; '.join(PREF_TEXT[p].replace('{pb}', str(case.get('preferred_budget_usd'))) for p in case['soft_prefs'])
    case['free_text'] = txt + '.'
    case['intended_conflict'] = True
    case['conflict_type'] = ctype
    case['conflict_description'] = ctype + ' - verified: no feasible package satisfies all of %s' % ', '.join(case['soft_prefs'])
    case['competing_prefs'] = sorted({p for f in det['acceptable_sacrifices'] for p in f})
    case['expected_status'] = 'OK_PLAN'
    case['expected_reason'] = ''
    notes = []
    if city == 'New York': notes.append('NYC short-stay lodging in the catalog is Jersey City (EWR mapping); NYC-market listings require >=30 nights')
    if case['wants_car']: notes.append('car capacity is an ESTIMATE by vehicle type; car picked up/returned at the arrival airport')
    if case['depart_flex_days'] or case['return_flex_days']: notes.append('date flexibility: depart +-%d / return +-%d days' % (case['depart_flex_days'], case['return_flex_days']))
    case['notes'] = '; '.join(notes)
    # package oracle (cheapest within budget) in the v1 shape + v2 fields
    feas = [p for p in pkgs if p['total'] <= case['budget_usd'] + 1e-9]
    best = min(feas, key=lambda p: (p['total'], p['km'], p['o']['ref'], p['b']['ref'], p['stay']))
    case['oracle_package'] = dict(status='FEASIBLE', nights=len(days) - 1, reasons=[], cheapest_total=best['total'],
                                  cheapest=pkg_summary(best, case['travelers']), combos_within_budget=det['n_feasible_packages'],
                                  budget_slack_pct=round(100 * (case['budget_usd'] - best['total']) / best['total'], 1),
                                  n_date_pairs=len(date_pairs(case['start_date'], case['end_date'], case['depart_flex_days'], case['return_flex_days'])))
    case['true_conflict'] = dict(passed=True, n_feasible_packages=det['n_feasible_packages'],
                                 n_feasible_without_car_variants=det['n_feasible_base_packages'], profiles=det['profiles'],
                                 acceptable_sacrifices=det['acceptable_sacrifices'], pareto_options=det['pareto_options'],
                                 cheapest_feasible=det['cheapest_feasible'], window_density=case.pop('_density'))
    case['oracle_places'] = places_oracle(case)
    order = ['id', 'split', 'group', 'city', 'origin', 'start_date', 'end_date', 'travelers', 'budget_usd', 'preferred_budget_usd', 'wants_car',
             'pace', 'interests', 'avoid', 'hotel_preference', 'soft_prefs', 'depart_flex_days', 'return_flex_days', 'as_of',
             'weather_fixture_needed', 'weather_fixture_files', 'weather_expected', 'free_text', 'intended_conflict', 'conflict_type',
             'conflict_description', 'competing_prefs', 'expected_status', 'expected_reason', 'notes', 'oracle_package', 'true_conflict', 'oracle_places']
    case.setdefault('preferred_budget_usd', None)
    if case['preferred_budget_usd'] == 10 ** 9: case['preferred_budget_usd'] = None
    return {k: case[k] for k in order}


def upgrade_v1(c):
    c = json.loads(json.dumps(c))
    c.setdefault('soft_prefs', []); c.setdefault('depart_flex_days', 0); c.setdefault('return_flex_days', 0); c.setdefault('preferred_budget_usd', None)
    c['conflict_type'] = c.get('conflict_description', '') if c['group'] == 'E' else ''
    c['competing_prefs'] = []; c['true_conflict'] = None
    if c['oracle_places'].get('status') == 'TO_BE_FILLED' and c['city'] in PLACES:
        c['oracle_places'] = places_oracle(c)
        c['notes'] = '; '.join(x for x in c['notes'].split('; ') if x and not x.startswith('place-dependent checks'))
    return c


def retest_v1(cases):
    """Apply the true-conflict test to the v1 conflicting cases (B-D) with the preferences they described:
    central (if requested; relaxed to soft), nonstop and long_days as generic soft prefs."""
    res = dict(n=0, passed=0, per_case={})
    for c in cases:
        if c['group'] not in 'BCD' or not c['intended_conflict']: continue
        cc = dict(c, hotel_preference='any', depart_flex_days=0, return_flex_days=0,
                  soft_prefs=(['central'] if c['hotel_preference'] == 'central' else []) + ['nonstop', 'long_days'])
        pk = vectors(cc, enumerate_packages(cc))
        ok, det = true_conflict_test(cc, pk)
        hard = dict(c, depart_flex_days=0, return_flex_days=0)
        n_hard = n_within(enumerate_packages(hard), c['budget_usd'])
        res['n'] += 1; res['passed'] += ok
        res['per_case'][c['id']] = dict(n_feasible_v1_hard=n_hard, passed=ok, reason=det.get('reason', ''),
                                        profiles=det.get('profiles'))
    return res


def write_csv(cases):
    flat = ['id', 'split', 'group', 'city', 'origin', 'start_date', 'end_date', 'travelers', 'budget_usd', 'preferred_budget_usd', 'wants_car',
            'pace', 'interests', 'avoid', 'hotel_preference', 'soft_prefs', 'depart_flex_days', 'return_flex_days', 'as_of', 'intended_conflict',
            'conflict_type', 'competing_prefs', 'expected_status', 'oracle_status', 'oracle_cheapest_total', 'n_feasible_packages',
            'acceptable_sacrifices', 'pareto_options', 'places_oracle', 'weather_flags', 'notes']
    with open(OUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=flat); w.writeheader()
        for c in cases:
            o = c['oracle_package']; tc = c.get('true_conflict') or {}
            w.writerow(dict({k: c.get(k) for k in flat if k in c}, interests=';'.join(c['interests']), avoid=';'.join(c['avoid']),
                            soft_prefs=';'.join(c.get('soft_prefs') or []), competing_prefs=';'.join(c.get('competing_prefs') or []),
                            oracle_status=o['status'], oracle_cheapest_total=o.get('cheapest_total', ''),
                            n_feasible_packages=tc.get('n_feasible_packages', o.get('combos_within_budget', '')),
                            acceptable_sacrifices=' | '.join('+'.join(s) for s in tc.get('acceptable_sacrifices', [])),
                            pareto_options=' | '.join('sacrifice %s: $%.2f' % ('+'.join(x['sacrifices']), x['cheapest']['total']) for x in tc.get('pareto_options', [])),
                            places_oracle=c['oracle_places']['status'],
                            weather_flags=' '.join('%s:%s' % (d[5:], '+'.join(v)) for d, v in c['weather_expected'].items())))


if __name__ == '__main__':
    main()
