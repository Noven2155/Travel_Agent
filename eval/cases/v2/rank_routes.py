#!/usr/bin/env python3
"""Rank origin -> destination route + date windows by the number of DISTINCT feasible packages
(outbound flights x return flights x lodging), T travelers, exact dates and with +-1 day flex on both ends
(multi-airport for New York). Lodging uses the same hard filters as tools.search_hotels (capacity, every
night available, min/max nights on check-in, <= 12 km from the center). No budget, no car.

    python eval/cases/v2/rank_routes.py [--T 2]   -> eval/cases/v2/route_ranking.json + printed top tables
"""
import argparse, json, os, sys, datetime as dt
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from analyze_data import MARKETS, inv, DATES, DI, STAYS, decode, hav  # noqa: E402

MAX_KM = 12.0
CITIES = ['Chicago', 'New York', 'Boston', 'San Francisco', 'Washington DC', 'Dallas-Fort Worth', 'Oakland']

def sh(d, k): return (dt.date.fromisoformat(d) + dt.timedelta(k)).isoformat()

def build(city, T):
    cfg = MARKETS[city]; ap = set(cfg['airports'])
    out, back = defaultdict(list), defaultdict(list)
    for f in inv['flights']:
        if f['seats'] <= 0 or f['seats'] < T: continue
        if f['destination'] in ap and f['arrivalDate'] == f['date']: out[(f['origin'], f['date'])].append(f)
        if f['origin'] in ap: back[(f['destination'], f['date'])].append(f)
    stays = []
    seen = set()
    for a in cfg['airports']:
        for k in inv['staysByAirport'].get(a, []):
            if k in seen: continue
            seen.add(k); s = STAYS[k]
            km = hav(*cfg['center'], s['lat'], s['lon'])
            if km > MAX_KM or (s['capacity'] or 0) < T: continue
            av, mn, mx = decode(s)
            stays.append((k, km, av, mn, mx))
    cache = {}
    def n_stays(ci, co):
        key = (ci, co)
        if key in cache: return cache[key]
        n = (dt.date.fromisoformat(co) - dt.date.fromisoformat(ci)).days; res = [0, 0]
        if ci in DI and co in DI and n > 0:
            i0 = DI[ci]
            for k, km, av, mn, mx in stays:
                if not (mn[i0] > 0 and mn[i0] <= n <= mx[i0]): continue
                if all(av[i0 + j] == 2 for j in range(n)):
                    res[0] += 1
                    if km <= cfg['central_km']: res[1] += 1
        cache[key] = res
        return res
    return out, back, n_stays

def rank(T):
    rows = []
    for city in CITIES:
        ap = set(MARKETS[city]['airports'])
        out, back, n_stays = build(city, T)
        origins = sorted({o for o, _ in out} - ap)
        for o in origins:
            for d in DATES:
                for nights in (2, 3, 4):
                    e = sh(d, nights)
                    if e not in DI: continue
                    no, nb = len(out.get((o, d), [])), len(back.get((o, e), []))
                    st, stc = n_stays(d, e) if no and nb else (0, 0)
                    exact = no * nb * st
                    flex = 0; flex_c = 0
                    for a in (-1, 0, 1):
                        for b in (-1, 0, 1):
                            d2, e2 = sh(d, a), sh(e, b)
                            if d2 not in DI or e2 not in DI or (dt.date.fromisoformat(e2) - dt.date.fromisoformat(d2)).days < 2: continue
                            O, B = len(out.get((o, d2), [])), len(back.get((o, e2), []))
                            if not (O and B): continue
                            s2, s2c = n_stays(d2, e2)
                            flex += O * B * s2; flex_c += O * B * s2c
                    if flex == 0: continue
                    rows.append(dict(city=city, origin=o, start=d, end=e, nights=nights, n_out=no, n_back=nb, n_stays=st,
                                     n_stays_central=stc, packages_exact=exact, packages_central_exact=no * nb * stc,
                                     packages_flex1=flex, packages_central_flex1=flex_c))
    return rows

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--T', type=int, default=2); a = ap.parse_args()
    rows = rank(a.T)
    # per city summary
    summ = {}
    for city in CITIES:
        r = [x for x in rows if x['city'] == city]
        tot_e = sum(x['packages_exact'] for x in r)
        summ[city] = dict(windows_with_pkg_exact=sum(1 for x in r if x['packages_exact'] > 0),
                          windows_exact_ge20=sum(1 for x in r if x['packages_exact'] >= 20),
                          windows_exact_ge20_with_central=sum(1 for x in r if x['packages_exact'] >= 20 and x['packages_central_exact'] > 0
                                                              and x['packages_central_exact'] < x['packages_exact']),
                          windows_flex_ge50=sum(1 for x in r if x['packages_flex1'] >= 50),
                          packages_exact_total=tot_e, packages_flex1_total=sum(x['packages_flex1'] for x in r))
    # per route (origin->city) aggregate
    route = defaultdict(lambda: dict(windows=0, pk_exact=0, pk_flex=0, best=0))
    for x in rows:
        k = (x['origin'], x['city']); r = route[k]
        r['windows'] += x['packages_exact'] > 0; r['pk_exact'] += x['packages_exact']; r['pk_flex'] += x['packages_flex1']
        r['best'] = max(r['best'], x['packages_exact'])
    routes = sorted(([o, c, v['windows'], v['pk_exact'], v['pk_flex'], v['best']] for (o, c), v in route.items()), key=lambda z: -z[3])
    top_w = sorted(rows, key=lambda x: (-x['packages_exact'], -x['packages_flex1']))[:30]
    top_city = {c: sorted((x for x in rows if x['city'] == c), key=lambda x: (-x['packages_exact'], -x['packages_flex1']))[:30] for c in CITIES}
    json.dump(dict(T=a.T, per_city=summ, routes=routes, top_windows=top_w, top_windows_per_city=top_city,
                   note='full per-window table is recomputed by this script (not stored: ~17.5k rows)'),
              open(os.path.join(HERE, 'route_ranking.json'), 'w'), indent=0)
    print('per city (T=%d):' % a.T)
    for c, s in summ.items(): print(' ', c, s)
    print('\ntop routes by total exact packages over all windows (origin, city, windows>0, pk_exact, pk_flex1, best window):')
    for r in routes[:20]: print(' ', r)
    print('\ntop windows:')
    for x in top_w[:20]: print(' ', {k: x[k] for k in ('city', 'origin', 'start', 'end', 'n_out', 'n_back', 'n_stays', 'n_stays_central', 'packages_exact', 'packages_flex1')})

if __name__ == '__main__':
    main()
