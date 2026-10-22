#!/usr/bin/env python3
"""Build eval set v3 - free-text segment (Travel Agent, team 8, BIU DS23). Additive: v1 and v2 stay frozen.

    python eval/cases/build_eval_cases_v3.py   -> eval/cases/eval_cases_v3.json / .csv + v3/build_log_v3.json

Each case = request_text (what the systems see, plus as_of) + hidden gold (structured fields the text implies and
2-3 key requirements with a deterministic checker id + params; eval/keyreq.py). Texts are hand-written in
v3_specs.py; route, dates and budget are filled in here from the densest (origin, window) combinations, reusing the
v2 oracle (eval/cases/build_eval_cases_v2.py: exhaustive package enumeration, Pareto test, places oracle):
  * >= MIN_FEASIBLE (10) feasible packages under the gold hard constraints (incl. no_early_flight_before, car);
  * places oracle PASS for the gold interests / avoid;
  * binding requirements: no_flight_departure_before only on windows whose cheapest package (without the rule)
    departs earlier; prio1 only where the cheapest feasible package violates the preference while a package that
    keeps it fits the budget; prio2 only on true conflicts (v2 test) whose cheapest Pareto option sacrifices the
    prioritised preference;
  * the pipeline (travel_agent.pipeline.build_candidates on the gold request) must agree with the oracle count.
as_of = start - 21 days (weather out of horizon: the free-text segment does not test weather). Deterministic.
"""
from __future__ import annotations

import csv, datetime as dt, hashlib, json, math, os, random, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, HERE)
import build_eval_cases_v2 as V2                 # noqa: E402  (oracle functions; its main() is not run)
from v3_specs import SPECS                       # noqa: E402
from travel_agent import config as C             # noqa: E402
from travel_agent import prefs as P              # noqa: E402
from travel_agent.models import TripRequest      # noqa: E402
from travel_agent.pipeline import build_candidates, weather_step  # noqa: E402
from travel_agent.tool_log import ToolLog        # noqa: E402

SEED = 20261031
MIN_FEASIBLE = 10            # v3 tests parsing, not option density (Chicago is sparse: 4 legs/day); v2 uses 20
MAX_ORIGIN_USE = 3
NIGHTS_ALT = [3, 2, 4]          # trip lengths tried (the spec's own first), densest window first within each
OUT_JSON = os.path.join(HERE, 'eval_cases_v3.json')
OUT_CSV = os.path.join(HERE, 'eval_cases_v3.csv')
OUT_LOG = os.path.join(HERE, 'v3', 'build_log_v3.json')
ORIG_NAME = dict(ATL='Atlanta', BOS='Boston', CLT='Charlotte', DEN='Denver', DFW='Dallas', DTW='Detroit', EWR='Newark',
                 IAD='Washington Dulles', JFK='JFK', LAX='Los Angeles', LGA='LaGuardia', MIA='Miami', OAK='Oakland',
                 ORD="O'Hare", PHL='Philadelphia', SFO='San Francisco')
MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def ordn(n): return '%d%s' % (n, 'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th'))


def fmt_dates(s, e, f):
    a, b = V2.s2d(s), V2.s2d(e)
    if f == 'md':
        return '%s %d-%d' % (MON[a.month - 1], a.day, b.day) if a.month == b.month else '%s %d - %s %d' % (MON[a.month - 1], a.day, MON[b.month - 1], b.day)
    if f == 'md2':
        return '%s %d to %s %d' % (MON[a.month - 1][:3], a.day, MON[b.month - 1][:3], b.day)
    if f == 'ord':
        return 'from the %s to the %s of %s' % (ordn(a.day), ordn(b.day), MON[b.month - 1]) if a.month == b.month else \
            'from %s %s to %s %s' % (MON[a.month - 1], ordn(a.day), MON[b.month - 1], ordn(b.day))
    return 'leaving %s, %s %d and flying home %s, %s %d' % (WD[a.weekday()], MON[a.month - 1], a.day, WD[b.weekday()], MON[b.month - 1], b.day)


def fmt_budget(b, f):
    return ('%.1fk' % (b / 1000)).replace('.0k', 'k') if f == 'k' else '${:,}'.format(b)


def dep_hm(f): return f['departure'][11:16]


def gold_request(spec, origin, s, e, budget):
    g = dict(city=spec['city'], origin=origin, start_date=s, end_date=e, travelers=spec['T'], budget_usd=budget,
             wants_car=spec['car'], pace=spec['pace'], interests=spec['interests'], avoid=spec.get('avoid', []),
             hotel_preference='any', as_of=V2.sh(s, -21), soft_prefs=list(spec.get('prefs', [])))
    g.update(spec.get('gold', {}))
    return g


def oracle_case(g):
    """v2-oracle dict for a gold request (plus the flex / weather fields it expects)."""
    return dict(g, depart_flex_days=0, return_flex_days=0, weather_fixture_needed=False, preferred_budget_usd=None)


def try_window(spec, origin, s):
    e = V2.sh(s, spec['nights'])
    g = gold_request(spec, origin, s, e, 10 ** 6)
    case = oracle_case(g)
    pk_all = V2.enumerate_packages(case)
    lim = g.get('no_early_flight_before')
    pk = [p for p in pk_all if not lim or (dep_hm(p['o']) >= lim and dep_hm(p['b']) >= lim)]
    if not pk:
        return None, 'no package'
    det = {}
    if lim:   # binding: the cheapest package without the rule departs earlier
        ch = min(pk_all, key=lambda p: p['total'])
        if dep_hm(ch['o']) >= lim and dep_hm(ch['b']) >= lim:
            return None, 'flight-time rule not binding'
    kind = spec['kind']
    if kind == 'std':
        cheapest = min(p['total'] for p in pk)
        budget = int(math.ceil(cheapest * 1.35 / 100.0) * 100)
    elif kind == 'prio1':
        case['soft_prefs'] = spec['prefs']
        V2.vectors(case, pk)
        ch = min(pk, key=lambda p: p['total'])
        keep = [p for p in pk if not p['sac']]
        if not ch['sac'] or not keep:
            return None, 'prio1 not binding'
        k = min(p['total'] for p in keep)
        budget = int(math.ceil(max(k * 1.15, ch['total'] * 1.35) / 100.0) * 100)
        det['cheapest_keeping'] = round(k, 2)
    else:   # prio2
        case['soft_prefs'] = spec['prefs']
        b = V2.design_budget(case, pk, 'budget')
        if b is None:     # structural conflict (no package satisfies both at any price): budget 1.3 x the front maximum
            b = V2.design_budget(case, pk, 'weather')
        if b is None:
            return None, 'no conflict budget'
        case['budget_usd'] = b
        ok, tc = V2.true_conflict_test(case, pk)
        if not ok:
            return None, 'true-conflict test: ' + tc.get('reason', '?')
        pref = spec['reqs'][0][1]['pref']
        opts = sorted(tc['pareto_options'], key=lambda o: o['cheapest']['total'])
        if pref not in opts[0]['sacrifices']:
            return None, 'prio2 not binding (cheapest Pareto option keeps %s)' % pref
        budget = b
        det['true_conflict'] = tc
    case['budget_usd'] = budget
    feas = [p for p in pk if p['total'] <= budget + 1e-9]
    nf = V2.n_within(feas, budget)
    if nf < MIN_FEASIBLE:
        return None, 'only %d feasible packages' % nf
    g['budget_usd'] = budget
    pl = V2.places_oracle(dict(case, budget_usd=budget))
    if pl['status'] != 'PASS':
        return None, 'places oracle FAIL'
    # the real pipeline must agree with the oracle
    req = TripRequest.model_validate(dict(g, request_id='X'))
    log = ToolLog('b')
    conds, _ = weather_step(log, req)
    cands = build_candidates(log, req, conditions=conds)
    if cands[0]['n_within_budget'] != nf:
        return None, 'pipeline count %d != oracle %d' % (cands[0]['n_within_budget'], nf)
    cheapest = min(feas, key=lambda p: (p['total'], p['km'], p['o']['ref'], p['b']['ref'], p['stay']))
    det.update(n_feasible_packages=nf, cheapest_feasible=V2.pkg_summary(cheapest, spec['T']), places=pl,
               pipeline_agrees=True, n_packages_without_flight_rule=len(pk_all) if lim else None)
    return (g, det), 'ok'


def key_requirements(spec, g, det):
    out = []
    for i, (chk, params) in enumerate(spec['reqs']):
        p = dict(params)
        if chk == 'budget_max':
            p['usd'] = g['budget_usd']
        if chk == 'priority_respected':
            tc = det['true_conflict']
            p['acceptable_sacrifices'] = [s for s in tc['acceptable_sacrifices'] if p['pref'] not in s]
            p['soft_prefs'] = g['soft_prefs']
        if chk == 'near_cheapest':
            p['cheapest_total'] = det['cheapest_feasible']['total']
        out.append(dict(id='%s-K%d' % (spec['id'], i + 1), checker=chk, params=p))
    return out


def main():
    rng = random.Random(SEED)
    ranked = {}
    used = {C.CITIES[c]['key']: [] for c in C.CITIES}
    origin_use = Counter()
    cases, log = [], dict(tested=0, failed=Counter(), per_case={})
    for spec in SPECS:
        wins = []
        for nights in [spec['nights']] + [n for n in NIGHTS_ALT if n != spec['nights']]:   # preferred length first
            key = (spec['city'], nights, spec['T'])
            if key not in ranked:
                ranked[key] = V2.ranked_windows(spec['city'], nights, spec['T'], 0, rng)
            wins += [(d, o, s, nights) for d, o, s in ranked[key]]
        got, tried, why_c = None, 0, Counter()
        for dens, origin, s, nights in wins:
            ck = C.CITIES[spec['city']]['key']
            if origin_use[(ck, origin)] >= MAX_ORIGIN_USE or any(abs((V2.s2d(s) - V2.s2d(u)).days) <= 1 for u in used[ck]):
                continue
            if V2.sh(s, -21) < V2.DATES[0] and False:
                continue
            tried += 1
            log['tested'] += 1
            res, why = try_window(dict(spec, nights=nights), origin, s)
            if res is None:
                log['failed'][why.split(' (')[0].split(':')[0]] += 1
                why_c[why[:50]] += 1
                continue
            got = (dens, origin, s, res)
            break
        if got is None:
            raise SystemExit('no window for %s: %s' % (spec['id'], dict(why_c)))
        dens, origin, s, (g, det) = got
        used[C.CITIES[spec['city']]['key']].append(s)
        origin_use[(C.CITIES[spec['city']]['key'], origin)] += 1
        text = spec['text'].format(orig=ORIG_NAME[origin], dates=fmt_dates(g['start_date'], g['end_date'], spec['dfmt']),
                                   budget=fmt_budget(g['budget_usd'], spec['bfmt']))
        TripRequest.model_validate(dict(g, request_id=spec['id']))
        cases.append(dict(id=spec['id'], split=spec['split'], group='F', segment='free_text', city=spec['city'],
                          phrasing_type=spec['phrasing'], request_text=text, as_of=g['as_of'],
                          expected_status='OK_PLAN', gold=dict(request=g, key_requirements=key_requirements(spec, g, det)),
                          oracle=dict(route_window_density=dens, **{k: v for k, v in det.items() if k != 'places'},
                                      places_status=det['places']['status'])))
        log['per_case'][spec['id']] = dict(windows_tried=tried, origin=origin, start=s, density=dens)
    meta = dict(version='v3', segment='free_text', built_with='eval/cases/build_eval_cases_v3.py', seed=SEED,
                specs='eval/cases/v3_specs.py', min_feasible=MIN_FEASIBLE, max_origin_use=MAX_ORIGIN_USE,
                v2_file='eval_cases_v2.json', v2_sha256=hashlib.sha256(open(os.path.join(HERE, 'eval_cases_v2.json'), 'rb').read()).hexdigest(),
                inventory_sha256=hashlib.sha256(open(C.INVENTORY_PATH, 'rb').read()).hexdigest(),
                visible_to_systems=['id', 'request_text', 'as_of'],
                note='gold.* and oracle.* are hidden from the systems (run_eval passes only id, request_text and as_of)')
    json.dump(dict(meta=meta, cases=cases), open(OUT_JSON, 'w'), indent=1, ensure_ascii=False, default=str)
    with open(OUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['id', 'split', 'city', 'phrasing_type', 'origin', 'start_date', 'end_date', 'travelers', 'budget_usd', 'n_feasible',
                    'key_requirements', 'request_text'])
        for c in cases:
            g = c['gold']['request']
            w.writerow([c['id'], c['split'], c['city'], c['phrasing_type'], g['origin'], g['start_date'], g['end_date'], g['travelers'],
                        g['budget_usd'], c['oracle']['n_feasible_packages'],
                        '; '.join('%s %s' % (k['checker'], json.dumps({a: b for a, b in k['params'].items() if a not in ('acceptable_sacrifices', 'soft_prefs')}))
                                  for k in c['gold']['key_requirements']), c['request_text']])
    log['failed'] = dict(log['failed'])
    os.makedirs(os.path.dirname(OUT_LOG), exist_ok=True)
    json.dump(log, open(OUT_LOG, 'w'), indent=1)
    print('cases', len(cases), Counter((c['split'], c['city'], c['phrasing_type']) for c in cases))
    print('tested windows', log['tested'], 'failed', log['failed'])


if __name__ == '__main__':
    main()
