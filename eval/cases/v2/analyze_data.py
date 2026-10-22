#!/usr/bin/env python3
"""Data analysis for the v2 eval cases: lodging (short-stay listings, distance to center, price spread) and
flight density per destination market, computed on data/inventory.json (the catalog the tools use).

    python eval/cases/v2/analyze_data.py   -> prints a table and writes eval/cases/v2/data_analysis.json
"""
import base64, json, math, statistics, struct, os, datetime as dt
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
inv = json.load(open(os.path.join(ROOT, 'data', 'inventory.json')))
DATES = inv['dates']; N = len(DATES); DI = {d: i for i, d in enumerate(DATES)}
STAYS = {s['key']: s for s in inv['stays']}

# candidate destination "cities": airports + a tourist center point (team decision for this analysis)
MARKETS = {
    'Chicago': dict(airports=['ORD'], center=(41.8819, -87.6278), center_name='Loop', central_km=5.0),
    'New York': dict(airports=['JFK', 'LGA', 'EWR'], center=(40.7580, -73.9855), center_name='Times Square', central_km=6.0),
    'Boston': dict(airports=['BOS'], center=(42.3550, -71.0656), center_name='Boston Common', central_km=5.0),
    'Los Angeles': dict(airports=['LAX'], center=(34.0522, -118.2437), center_name='Downtown LA', central_km=5.0),
    'San Francisco': dict(airports=['SFO'], center=(37.7880, -122.4075), center_name='Union Square', central_km=5.0),
    'Denver': dict(airports=['DEN'], center=(39.7392, -104.9903), center_name='Civic Center', central_km=5.0),
    'Washington DC': dict(airports=['IAD'], center=(38.8895, -77.0353), center_name='National Mall', central_km=5.0),
    'Oakland': dict(airports=['OAK'], center=(37.8044, -122.2712), center_name='Downtown Oakland', central_km=5.0),
    'Dallas-Fort Worth': dict(airports=['DFW'], center=(32.7767, -96.7970), center_name='Downtown Dallas', central_km=5.0),
}

def hav(a, b, c, d):
    p = math.radians
    x = math.sin(p(c - a) / 2) ** 2 + math.cos(p(a)) * math.cos(p(c)) * math.sin(p(d - b) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(x))

def decode(s):
    b = base64.b64decode(s['availabilityPacked'])
    av = [(b[i // 4] >> (2 * (i % 4))) & 3 for i in range(N)]
    mn = struct.unpack('<%dH' % N, base64.b64decode(s['minNightsPacked']))
    mx = struct.unpack('<%dH' % N, base64.b64decode(s['maxNightsPacked']))
    return av, mn, mx

def q(xs, p):
    xs = sorted(xs)
    if not xs: return None
    return round(xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))], 1)

def lodging(city, cfg):
    keys = []
    for a in cfg['airports']:
        for k in inv['staysByAirport'].get(a, []):
            if k not in keys: keys.append(k)
    rows = []
    for k in keys:
        s = STAYS[k]; av, mn, mx = decode(s)
        valid = [i for i in range(N) if mn[i] > 0]
        med_min = statistics.median([mn[i] for i in valid]) if valid else 999
        short_dates = sum(1 for i in range(N) if 0 < mn[i] <= 5 and av[i] == 2)
        rows.append(dict(key=k, market=s['market'], km=hav(*cfg['center'], s['lat'], s['lon']), price=s['price'],
                         cap=s['capacity'] or 0, med_min=med_min, short=med_min <= 5, short_dates=short_dates))
    short = [r for r in rows if r['short']]
    s12 = [r for r in short if r['km'] <= 12]
    cen = [r for r in s12 if r['km'] <= cfg['central_km']]
    far = [r for r in s12 if r['km'] > cfg['central_km']]
    by_market = Counter(r['market'] for r in s12)
    return dict(listings=len(rows), short_stay=len(short), short_le12km=len(s12), short_central=len(cen),
                short_le12km_cap4=sum(1 for r in s12 if r['cap'] >= 4),
                km_p10_p50_p90=[q([r['km'] for r in short], x) for x in (.1, .5, .9)],
                price_p10_p50_p90_le12=[q([r['price'] for r in s12], x) for x in (.1, .5, .9)],
                price_median_central=q([r['price'] for r in cen], .5), price_median_outside=q([r['price'] for r in far], .5),
                min_price_central=min([r['price'] for r in cen], default=None), min_price_outside=min([r['price'] for r in far], default=None),
                markets_le12=dict(by_market))

def flights(city, cfg, T=2, nights=3):
    ap = set(cfg['airports'])
    out = defaultdict(list); back = defaultdict(list)
    for f in inv['flights']:
        if f['seats'] < T or f['seats'] <= 0: continue
        if f['destination'] in ap and f['arrivalDate'] == f['date']:
            out[(f['origin'], f['date'])].append(f)
        if f['origin'] in ap:
            back[(f['destination'], f['date'])].append(f)
    per_day_legs = Counter()
    for (o, d), v in out.items(): per_day_legs[d] += len(v)
    per_route_date = [len(v) for v in out.values()]
    origins = sorted({o for o, _ in out})
    def shift(d, k): return (dt.date.fromisoformat(d) + dt.timedelta(k)).isoformat()
    win0 = win_choice0 = win_flex = win_choice_flex = win_nonstop_mix = 0
    for o in origins:
        if o in ap: continue
        for d in DATES:
            e = shift(d, nights)
            if e not in DI: continue
            no, nb = len(out.get((o, d), [])), len(back.get((o, e), []))
            if no and nb:
                win0 += 1
                if no * nb >= 4: win_choice0 += 1
                fo = out.get((o, d), []) + back.get((o, e), [])
                if any(f['nonstop'] for f in fo) and any(not f['nonstop'] for f in fo): win_nonstop_mix += 1
            # flex +-1 on both ends (dates shift, nights may change by +-1..2 -> keep nights>=2)
            O = [x for k in (-1, 0, 1) for x in out.get((o, shift(d, k)), [])]
            B = [x for k in (-1, 0, 1) for x in back.get((o, shift(e, k)), [])]
            if O and B:
                win_flex += 1
                if len(O) * len(B) >= 4: win_choice_flex += 1
    return dict(origins=len([o for o in origins if o not in ap]), legs_in=sum(len(v) for v in out.values()),
                legs_per_day_median=statistics.median([per_day_legs.get(d, 0) for d in DATES]),
                legs_per_route_date_median_when_any=statistics.median(per_route_date) if per_route_date else 0,
                share_route_dates_ge2=round(sum(1 for x in per_route_date if x >= 2) / max(1, len(per_route_date)), 3),
                nonstop_share=round(sum(f['nonstop'] for v in out.values() for f in v) / max(1, sum(len(v) for v in out.values())), 3),
                windows_3n_exact=win0, windows_3n_exact_ge4_flight_pairs=win_choice0, windows_3n_exact_nonstop_mix=win_nonstop_mix,
                windows_3n_flex1=win_flex, windows_3n_flex1_ge4_flight_pairs=win_choice_flex)

def main():
    res = {}
    for city, cfg in MARKETS.items():
        res[city] = dict(airports=cfg['airports'], center=cfg['center_name'], central_km=cfg['central_km'],
                         lodging=lodging(city, cfg), flights=flights(city, cfg))
    json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_analysis.json'), 'w'), indent=1)
    hdr = ['city', 'listings', 'short<=5n', 'short<=12km', 'central', 'cap>=4', 'km p10/50/90', 'price p10/50/90', 'med$ cen/out',
           'min$ cen/out', 'legs/day', 'route-date>=2', 'nonstop%', 'win3n', 'win3n>=4pairs', 'flex1>=4pairs']
    print(' | '.join(hdr))
    for c, r in res.items():
        L, F = r['lodging'], r['flights']
        print(' | '.join(map(str, [c, L['listings'], L['short_stay'], L['short_le12km'], L['short_central'], L['short_le12km_cap4'],
              L['km_p10_p50_p90'], L['price_p10_p50_p90_le12'], f"{L['price_median_central']}/{L['price_median_outside']}",
              f"{L['min_price_central']}/{L['min_price_outside']}", F['legs_per_day_median'], F['share_route_dates_ge2'],
              F['nonstop_share'], F['windows_3n_exact'], F['windows_3n_exact_ge4_flight_pairs'], F['windows_3n_flex1_ge4_flight_pairs']])))
        print('    markets<=12km:', L['markets_le12'])

if __name__ == '__main__':
    main()
