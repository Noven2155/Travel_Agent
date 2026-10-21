#!/usr/bin/env python3
"""Build the frozen eval set (40) + dev set (8) for the Travel Agent project (team 8, BIU DS23).

Reads only local files:
  - inventory.json (flights / stays / cars catalog, 2022 dates)
  - weather_preview/{chicago,nyc}_2022_daily_raw.json (Open-Meteo Historical Forecast API, CC BY 4.0)
  - places_data/{chicago,nyc}_places.csv if present (OSM + Wikivoyage; ratings are synthetic and unused)

For every case it runs an exhaustive package oracle over flights x lodging (x car) and writes
eval_cases.json / eval_cases.csv. Deterministic: same inputs -> same output.

Conventions (mirror the planned tools; change here and in the tools together):
  * round trip = two one-way catalog records (outbound origin->city on start_date, return city->origin on end_date)
  * outbound must arrive on start_date (arrivalDate == date); seats >= travelers; seats == 0 is treated as unknown -> excluded
  * nights = end_date - start_date; every night must be in the catalog date list with state 'available'
    (availabilityPacked, 2 bits/date, low bits first: 0 unknown, 1 unavailable, 2 available - verified against the daily CSV);
    minNights[check_in] <= nights <= maxNights[check_in] (packed per date, uint16 LE); capacity >= travelers
  * car: listing in carsByAirport[airport]; no blackout overlapping [start_date, end_date] (inclusive);
    rental_days = nights + 1 (catalog convention); capacity is an ESTIMATE from vehicle type (capacityEstimate);
    MVP: wants_car only for travelers <= 4, else NEEDS_DATA; with a car, outbound and return use the same airport
  * total = (fare_out + fare_back) * travelers + stay_price * nights + car_daily_rate * rental_days  (no fees in source)
  * central = haversine(stay, city_center) <= CENTRAL_RADIUS_KM[city]  (threshold = team decision)
"""
import base64, csv, json, math, os, random, struct, sys, datetime as dt
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
TRAVEL = os.path.dirname(HERE)
INV = os.environ.get('INVENTORY', os.path.join(TRAVEL, 'newdata/tourism_project_data_package/data/inventory.json'))
PLACES_DIR = os.path.join(TRAVEL, 'places_data')
WX_DIR = os.path.join(HERE, 'weather_preview')

CITIES = {
    'Chicago': dict(key='chicago', airports=['ORD'], stay_airports=['ORD'], center=(41.8819, -87.6278), center_name='Loop (State & Madison)'),
    'New York': dict(key='nyc', airports=['JFK', 'LGA', 'EWR'], stay_airports=['JFK', 'LGA', 'EWR'], center=(40.7580, -73.9855), center_name='Times Square'),
}
CENTRAL_RADIUS_KM = {'Chicago': 5.0, 'New York': 6.0}
MAX_STAY_KM = 12.0       # every stay must be within this distance of the city center (commute rule, team decision)
MAX_CAR_TRAVELERS = 4
AS_OF_FAR_DAYS = 30      # non-weather cases: every trip day OUT_OF_HORIZON
AS_OF_NEAR_DAYS = 2      # weather cases: every trip day has lead <= 7 (nights <= 5)
HORIZON = 7
RAIN_MM, RAIN_H, HEAT_C, WIND_KMH = 5.0, 3.0, 35.0, 60.0
SLOTS = {'relaxed': 2, 'normal': 3, 'packed': 5}   # max non-meal activities per full day (team decision)
COVERAGE_MIN = 0.75
VOCAB = ['food', 'culture', 'attractions', 'nightlife', 'family', 'nature', 'shows', 'shopping', 'extreme/adventure']
SEED = 20261030

def d2s(d): return d.isoformat()
def s2d(s): return dt.date.fromisoformat(s)
def ceil10(x): return int(math.ceil(x / 10.0) * 10)
def floor10(x): return int(math.floor(x / 10.0) * 10)
def hav(a, b, c, e):
    p = math.radians; R = 6371.0
    x = math.sin(p(c - a) / 2) ** 2 + math.cos(p(a)) * math.cos(p(c)) * math.sin(p(e - b) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))

# ---------------------------------------------------------------- catalog
inv = json.load(open(INV))
DATES = inv['dates']; DI = {x: i for i, x in enumerate(DATES)}
N = len(DATES)
FLIGHTS = inv['flights']
for i, f in enumerate(FLIGHTS): f['ref'] = 'F%d' % i
STAYS = {s['key']: s for s in inv['stays']}
CARS = {c['id']: c for c in inv['cars']}
ORIGINS = [o['code'] for o in inv['originAirports']]

def decode(s):
    b = base64.b64decode(s['availabilityPacked'])
    av = [(b[i // 4] >> (2 * (i % 4))) & 3 for i in range(N)]
    mn = struct.unpack('<%dH' % N, base64.b64decode(s['minNightsPacked']))
    mx = struct.unpack('<%dH' % N, base64.b64decode(s['maxNightsPacked']))
    return av, mn, mx
DEC = {}
for city, cfg in CITIES.items():
    for a in cfg['stay_airports']:
        for k in inv['staysByAirport'][a]:
            if k not in DEC: DEC[k] = decode(STAYS[k])

FL_OUT, FL_BACK = {}, {}
for f in FLIGHTS:
    FL_OUT.setdefault((f['origin'], f['destination'], f['date']), []).append(f)

def flights_out(origin, airport, date, T):
    return [f for f in FL_OUT.get((origin, airport, date), []) if f['seats'] >= T and f['seats'] > 0 and f['arrivalDate'] == date]
def flights_back(airport, origin, date, T):
    return [f for f in FL_OUT.get((airport, origin, date), []) if f['seats'] >= T and f['seats'] > 0]

def city_stays(city):
    ks = []
    for a in CITIES[city]['stay_airports']:
        for k in inv['staysByAirport'][a]:
            if k not in ks: ks.append(k)
    return ks
CITY_STAYS = {c: city_stays(c) for c in CITIES}

def stay_dist(city, s): return hav(CITIES[city]['center'][0], CITIES[city]['center'][1], s['lat'], s['lon'])

def stays_ok(city, start, end, T, central):
    nights = (s2d(end) - s2d(start)).days
    if start not in DI: return []
    ci = DI[start]; out = []
    for k in CITY_STAYS[city]:
        s = STAYS[k]; av, mn, mx = DEC[k]
        if s['capacity'] is None or s['capacity'] < T: continue
        if not (mn[ci] > 0 and mx[ci] > 0 and mn[ci] <= nights <= mx[ci]): continue
        ok = True
        for j in range(nights):
            dd = d2s(s2d(start) + dt.timedelta(j))
            if dd not in DI or av[DI[dd]] != 2: ok = False; break
        if not ok: continue
        dist = stay_dist(city, s)
        if dist > MAX_STAY_KM: continue
        if central and dist > CENTRAL_RADIUS_KM[city]: continue
        out.append((s, dist))
    return out

def cars_ok(airport, start, end):
    out = []
    for cid in inv['carsByAirport'].get(airport, []):
        c = CARS[cid]
        if any(not (b[1] < start or b[0] > end) for b in c['blackouts']): continue
        out.append(c)
    return out

# ---------------------------------------------------------------- weather preview
WX = {}
for city, cfg in CITIES.items():
    p = os.path.join(WX_DIR, '%s_2022_daily_raw.json' % cfg['key'])
    dd = json.load(open(p))['daily']
    WX[city] = {}
    for i, t in enumerate(dd['time']):
        fl = []
        if (dd['precipitation_sum'][i] or 0) >= RAIN_MM or (dd['precipitation_hours'][i] or 0) >= RAIN_H: fl.append('RAIN')
        if (dd['apparent_temperature_max'][i] or 0) >= HEAT_C: fl.append('HEAT')
        if (dd['wind_gusts_10m_max'][i] or 0) >= WIND_KMH: fl.append('WIND')
        WX[city][t] = dict(flags=fl, precip_mm=dd['precipitation_sum'][i], precip_h=dd['precipitation_hours'][i],
                           apparent_max=dd['apparent_temperature_max'][i], gust_max=dd['wind_gusts_10m_max'][i])

def trip_days(start, end):
    n = (s2d(end) - s2d(start)).days
    return [d2s(s2d(start) + dt.timedelta(i)) for i in range(n + 1)]

# ---------------------------------------------------------------- places (optional)
PLACES = {}
for city, cfg in CITIES.items():
    p = os.path.join(PLACES_DIR, '%s_places.csv' % cfg['key'])
    if os.path.exists(p):
        PLACES[city] = list(csv.DictReader(open(p, encoding='utf-8')))

def places_oracle(case):
    city = case['city']
    if city not in PLACES:
        return dict(status='TO_BE_FILLED', reason='%s_places.csv not available yet' % CITIES[city]['key'])
    rows = PLACES[city]; avoid = set(case['avoid'])
    def tags(r): return set(t for t in r['tags'].split(';') if t)
    usable = [r for r in rows if not (tags(r) & avoid)]
    per = {}
    for t in case['interests']:
        rs = [r for r in usable if t in tags(r)]
        per[t] = dict(total=len(rs), indoor_true=sum(r['indoor'] == 'true' for r in rs),
                      outdoor_or_unknown=sum(r['indoor'] != 'true' for r in rs))
    days = trip_days(case['start_date'], case['end_date'])
    rain_days = [d for d in days if case['weather_fixture_needed'] and 'RAIN' in WX[city][d]['flags']]
    dry_days = [d for d in days if d not in rain_days]
    full_days = max(0, len(days) - 2)
    slots = full_days * SLOTS[case['pace']] + 2   # arrival + departure day: 1 activity each (estimate)
    need = math.ceil(COVERAGE_MIN * len(case['interests']))
    coverable = [t for t in case['interests'] if per[t]['total'] > 0 and (per[t]['indoor_true'] > 0 or dry_days)]
    ok = slots >= need and len(coverable) >= need
    return dict(status='PASS' if ok else 'FAIL', activity_slots_estimate=slots, interests_needed=need,
                coverable_interests=coverable, per_interest=per, rain_days=rain_days, dry_days=len(dry_days),
                note='necessary-condition check (slots + tag/indoor availability), not a full schedule; ratings not used')

# ---------------------------------------------------------------- package oracle
def best_package(case, budget=None, count=False):
    """Exhaustive over all flights x stays (x cars). Returns cheapest feasible package and, if count, #combos <= budget."""
    city, T, start, end = case['city'], case['travelers'], case['start_date'], case['end_date']
    nights = (s2d(end) - s2d(start)).days
    res = dict(nights=nights, reasons=[])
    if case['wants_car'] and T > MAX_CAR_TRAVELERS:
        res.update(status='NEEDS_DATA', reasons=['car requested for %d travelers; MVP supports <=%d (capacity is only an estimate)' % (T, MAX_CAR_TRAVELERS)])
        return res
    airports = CITIES[city]['airports']
    outs = {a: flights_out(case['origin'], a, start, T) for a in airports}
    backs = {a: flights_back(a, case['origin'], end, T) for a in airports}
    stays = stays_ok(city, start, end, T, case['hotel_preference'] == 'central')
    res.update(n_out_flights=sum(map(len, outs.values())), n_back_flights=sum(map(len, backs.values())), n_stays=len(stays))
    cars = {}
    if case['wants_car']:
        cars = {a: [c for c in cars_ok(a, start, end) if c['capacityEstimate'] >= T] for a in airports}
        res['n_cars'] = sum(len(cars[a]) for a in airports if outs[a] and backs[a])
    if not res['n_out_flights']: res['reasons'].append('no outbound flight %s->%s on %s for %d' % (case['origin'], '/'.join(airports), start, T))
    if not res['n_back_flights']: res['reasons'].append('no return flight %s->%s on %s for %d' % ('/'.join(airports), case['origin'], end, T))
    if not stays: res['reasons'].append('no lodging matching capacity/min-nights/availability%s' % (' within central radius' if case['hotel_preference'] == 'central' else ''))
    rental_days = nights + 1
    combos = []   # (total, out, back, stay, car)
    best = None; n_within = 0; n_total = 0
    pairs = []
    if case['wants_car']:
        for a in airports:
            for c in cars.get(a, []):
                pairs.append((outs[a], backs[a], c))
    else:
        pairs.append(([f for a in airports for f in outs[a]], [f for a in airports for f in backs[a]], None))
    for O, B, c in pairs:
        if not O or not B: continue
        carcost = c['dailyRate'] * rental_days if c else 0.0
        for o in O:
            for b in B:
                fl = (o['fare'] + b['fare']) * T
                for s, dist in stays:
                    tot = fl + s['price'] * nights + carcost
                    n_total += 1
                    if budget is not None and tot <= budget + 1e-9: n_within += 1
                    if best is None or tot < best[0]: best = (tot, o, b, s, dist, c)
    if case['wants_car'] and not any(cars.get(a) for a in airports) and not res['reasons']:
        res['reasons'].append('no available car at arrival airport')
    if best is None:
        if not res['reasons']: res['reasons'].append('no airport-consistent combination (car must be picked up/returned at the arrival airport)')
        res.update(status='NO_PACKAGE_IN_CATALOG'); return res
    tot, o, b, s, dist, c = best
    res.update(status='FEASIBLE', cheapest_total=round(tot, 2), combos_total=n_total,
               cheapest=dict(flight_out=o['ref'], out_airport=o['destination'], out_fare=o['fare'], out_nonstop=o['nonstop'],
                             flight_back=b['ref'], back_airport=b['origin'], back_fare=b['fare'],
                             stay=s['key'], stay_market=s['market'], stay_price=s['price'], stay_km_to_center=round(dist, 1),
                             car=('C' + c['id']) if c else None, car_type=c['type'] if c else None,
                             car_capacity_estimate=c['capacityEstimate'] if c else None,
                             car_daily_rate=c['dailyRate'] if c else None, rental_days=rental_days if c else None))
    if budget is not None:
        res['combos_within_budget'] = n_within
        if n_within == 0:
            res['status'] = 'NO_PACKAGE_IN_CATALOG'; res['reasons'].append('budget %d below cheapest catalog package %.2f' % (budget, tot))
    return res

# ---------------------------------------------------------------- case templates
# (id, split, group, city, T, nights, car, hotel, pace, interests, avoid, weather, budget_mode, conflict)
# weather: None (as_of far) | 'dry' | 'rain' | 'rain2' (>=2 rain days) | 'heat' | 'wind'
# budget_mode: comfy (x1.6 cheapest) | mid (x1.3) | tight (x1.04 cheapest satisfying hard constraints) | below (x0.85) | fixed
T = []
def add(*a): T.append(a)
C, NY = 'Chicago', 'New York'
# ---- eval A: simple, no intended conflict (12: 7 CHI / 5 NYC; 4 car; weather 1 rain + 1 dry)
add('A01','eval','A',C,1,3,False,'any','normal',['culture','food'],[],None,'comfy',None)
add('A02','eval','A',C,2,4,True,'any','normal',['nature','food'],[],None,'comfy',None)
add('A03','eval','A',C,1,3,False,'any','packed',['culture','attractions','shows'],[],None,'comfy',None)
add('A04','eval','A',C,2,3,False,'any','normal',['food','nightlife'],[],'rain','comfy',None)
add('A05','eval','A',C,3,4,True,'any','normal',['family','attractions'],['nightlife'],None,'comfy',None)
add('A06','eval','A',C,1,2,False,'any','normal',['culture'],[],None,'comfy',None)
add('A07','eval','A',C,2,3,False,'any','relaxed',['food','shopping'],[],None,'comfy',None)
add('A08','eval','A',NY,1,3,False,'any','normal',['culture','food'],[],None,'comfy',None)
add('A09','eval','A',NY,2,4,True,'any','normal',['attractions','food'],[],None,'comfy',None)
add('A10','eval','A',NY,2,3,False,'any','normal',['shows','nightlife'],[],'dry','comfy',None)
add('A11','eval','A',NY,1,2,False,'any','packed',['culture','shopping','food'],[],None,'comfy',None)
add('A12','eval','A',NY,3,3,True,'any','normal',['family','nature'],['nightlife'],None,'comfy',None)
# ---- eval B: low budget vs central lodging / day load (12: 7/5; 3 car; weather 1 rain + 1 heat)
add('B01','eval','B',C,2,3,False,'central','relaxed',['culture','food'],[],None,'tight','low budget + central lodging + relaxed pace')
add('B02','eval','B',C,1,3,False,'central','normal',['food','nightlife'],[],None,'tight','low budget + central lodging')
add('B03','eval','B',C,2,2,False,'any','relaxed',['culture','food','nature','shows'],[],None,'tight','4 interests in 3 days at relaxed pace + tight budget (load vs coverage)')
add('B04','eval','B',C,2,3,True,'central','normal',['culture','attractions'],[],None,'tight','low budget + central lodging + car')
add('B05','eval','B',C,1,4,False,'central','relaxed',['nature','food','culture'],[],'rain','tight','low budget + central lodging + rain day vs outdoor interest')
add('B06','eval','B',C,2,3,False,'any','relaxed',['nature','attractions'],[],'heat','tight','tight budget + heat day vs outdoor interests at relaxed pace')
add('B07','eval','B',C,3,3,True,'central','relaxed',['family','food'],['nightlife'],None,'tight','3 travelers + car + central lodging + low budget')
add('B08','eval','B',NY,1,3,False,'central','relaxed',['culture','food'],[],None,'tight','low budget + central lodging')
add('B09','eval','B',NY,2,3,False,'central','normal',['shows','food','nightlife'],[],None,'tight','low budget + central lodging')
add('B10','eval','B',NY,2,2,False,'any','relaxed',['culture','food','shopping','attractions'],[],None,'tight','4 interests in 3 days at relaxed pace + tight budget (load vs coverage)')
add('B11','eval','B',NY,2,4,True,'central','relaxed',['attractions','food'],[],None,'tight','low budget + central lodging + car')
add('B12','eval','B',NY,1,3,False,'central','relaxed',['nature','culture'],[],None,'tight','low budget + central lodging')
# ---- eval C: car under conflict, travelers <= 4 (6: 4/2; all car; weather 1 rain)
add('C01','eval','C',C,4,3,True,'any','normal',['family','attractions'],['nightlife'],None,'tight','4 travelers + car (estimated capacity) + tight budget')
add('C02','eval','C',C,3,4,True,'central','normal',['culture','food'],[],None,'tight','car + central lodging + tight budget (car cost vs location)')
add('C03','eval','C',C,2,3,True,'any','relaxed',['nature','food'],[],'rain','tight','car + tight budget + rain day vs nature')
add('C04','eval','C',C,4,2,True,'any','normal',['culture','shows'],[],None,'tight','4 travelers + car + short trip + tight budget')
add('C05','eval','C',NY,4,3,True,'any','normal',['attractions','family'],['nightlife'],None,'tight','4 travelers + car + tight budget')
add('C06','eval','C',NY,3,3,True,'central','relaxed',['food','culture'],[],None,'tight','car + central lodging + tight budget')
# ---- eval D: weather vs outdoor preferences (6: 4/2; 2 car; 5 rain + 1 wind)
add('D01','eval','D',C,2,3,False,'any','normal',['nature','attractions'],[],'rain2','mid','outdoor interests, >=2 rain days in forecast')
add('D02','eval','D',C,1,4,False,'any','relaxed',['nature','food'],[],'rain2','mid','nature at relaxed pace, >=2 rain days')
add('D03','eval','D',C,2,3,True,'any','normal',['nature','family'],[],'rain','mid','nature + family outdoors, rain day, car')
add('D04','eval','D',C,1,3,False,'any','normal',['nature','culture'],[],'wind','mid','outdoor interest on a windy day (flag only)')
add('D05','eval','D',NY,2,3,False,'any','normal',['nature','attractions'],[],'rain2','mid','outdoor interests, >=2 rain days')
add('D06','eval','D',NY,1,3,True,'any','relaxed',['nature','food'],[],'rain','mid','nature + car, rain day')
# ---- eval E: intentionally infeasible (4: 2/2; 2 car)
add('E01','eval','E',C,1,3,False,'any','normal',['culture','food'],[],None,'fixed:1500','E:no_return_origin')
add('E02','eval','E',C,2,3,True,'any','normal',['culture','food'],[],None,'below','E:budget_below_cheapest')
add('E03','eval','E',NY,5,3,True,'any','normal',['family','attractions'],[],None,'fixed:4000','E:car_over_4')
add('E04','eval','E',NY,2,3,False,'any','normal',['culture','shows'],[],None,'fixed:2500','E:no_return_origin')
# ---- dev (8: 5 CHI / 3 NYC), never used for reporting
add('V01','dev','A',C,2,3,False,'any','normal',['culture','food'],[],None,'comfy',None)
add('V02','dev','B',C,1,3,False,'central','relaxed',['food','culture'],[],None,'tight','low budget + central lodging')
add('V03','dev','C',C,3,3,True,'any','normal',['family','attractions'],[],None,'tight','car + tight budget')
add('V04','dev','D',C,2,3,False,'any','normal',['nature','attractions'],[],'rain','mid','outdoor interests, rain day')
add('V05','dev','E',C,6,3,True,'any','normal',['family','food'],[],None,'fixed:5000','E:car_over_4')
add('V06','dev','A',NY,1,3,False,'any','normal',['culture','shows'],[],None,'comfy',None)
add('V07','dev','B',NY,2,3,False,'central','relaxed',['food','culture'],[],None,'tight','low budget + central lodging')
add('V08','dev','D',NY,2,3,False,'any','normal',['nature','food'],[],'rain','mid','outdoor interests, rain day')

FREE_TEXT = {'culture': 'museums and galleries', 'food': 'local food', 'attractions': 'the classic sights', 'nightlife': 'bars in the evening',
             'family': 'kid-friendly places', 'nature': 'parks and the waterfront', 'shows': 'a show or concert', 'shopping': 'some shopping',
             'extreme/adventure': 'something active'}
AVOID_TEXT = {'nightlife': 'no bars', 'shopping': 'no malls'}

def weather_ok(city, start, end, w):
    days = trip_days(start, end); fl = [WX[city][d]['flags'] for d in days]
    nrain = sum('RAIN' in f for f in fl); anyflag = any(fl)
    if w is None: return True
    if w == 'dry': return not anyflag
    nrain_inner = sum('RAIN' in f for f in fl[:-1])   # rain on a day other than the departure day
    if w == 'rain': return nrain_inner >= 1 and nrain < len(days)
    if w == 'rain2': return nrain_inner >= 2 and nrain < len(days)
    if w == 'heat': return any('HEAT' in f for f in fl) and nrain == 0
    if w == 'wind': return any('WIND' in f for f in fl) and nrain == 0
    return False

def main():
    rng = random.Random(SEED)
    used_windows = set(); origin_use = Counter(); month_use = Counter(); cases = []
    for (cid, split, grp, city, Tn, nights, car, hotel, pace, interests, avoid, w, bmode, conflict) in T:
        e_kind = conflict[2:] if conflict and conflict.startswith('E:') else None
        if e_kind == 'no_return_origin':
            # origins with outbound flights into the city but no return records at all (not covered as destinations)
            cand_origins = [o for o in ORIGINS if not any(f['origin'] in CITIES[city]['airports'] and f['destination'] == o for f in FLIGHTS)]
        else:
            cand_origins = [o for o in ORIGINS if o not in CITIES[city]['airports']]
        windows = [(o, s) for o in cand_origins for s in DATES]
        rng.shuffle(windows)
        windows.sort(key=lambda x: (origin_use[(city, x[0])], month_use[(city, x[1][:7])]))
        chosen = None
        for o, s in windows:
            e = d2s(s2d(s) + dt.timedelta(nights))
            if (city, s) in used_windows or e not in DI: continue
            if s2d(e) > s2d(DATES[-1]): continue
            if not weather_ok(city, s, e, w): continue
            case = dict(id=cid, split=split, group=grp, city=city, origin=o, start_date=s, end_date=e, travelers=Tn,
                        wants_car=car, pace=pace, interests=interests, avoid=avoid, hotel_preference=hotel)
            if e_kind == 'no_return_origin':
                if not flights_out(o, None, s, Tn) and not any(flights_out(o, a, s, Tn) for a in CITIES[city]['airports']): continue
                pk = best_package(case)
                if pk['status'] != 'NO_PACKAGE_IN_CATALOG': continue
            elif e_kind == 'car_over_4':
                # make sure the same trip WITHOUT the car would be feasible, so the only blocker is car capacity
                pk0 = best_package(dict(case, wants_car=False))
                if pk0['status'] != 'FEASIBLE': continue
                pk = best_package(case)
            else:
                pk = best_package(case)
                if pk['status'] != 'FEASIBLE': continue
                if bmode == 'tight' and grp == 'B' and hotel == 'central':
                    any_pk = best_package(dict(case, hotel_preference='any'))
                    if pk['cheapest_total'] < 1.10 * any_pk['cheapest_total']: continue   # central must cost >=10% more
                    case['_cheapest_any'] = any_pk['cheapest_total']
                if car and grp == 'C':
                    nocar = best_package(dict(case, wants_car=False))
                    case['_cheapest_no_car'] = nocar.get('cheapest_total')
                if grp in 'AB' and pk['n_stays'] < 1: continue
            chosen = (case, pk); break
        if not chosen:
            print('!! no window found for', cid, file=sys.stderr); continue
        case, pk = chosen
        used_windows.add((city, case['start_date'])); origin_use[(city, case['origin'])] += 1; month_use[(city, case['start_date'][:7])] += 1
        # budget
        base = pk.get('cheapest_total')
        if e_kind == 'car_over_4': budget = ceil10(pk0['cheapest_total'] * 1.6)   # generous: only the car blocks
        elif bmode.startswith('fixed:'): budget = int(bmode.split(':')[1])
        elif bmode == 'comfy': budget = ceil10(base * 1.6)
        elif bmode == 'mid': budget = ceil10(base * 1.3)
        elif bmode == 'tight': budget = ceil10(base * 1.04)
        elif bmode == 'below': budget = floor10(base * 0.85)
        case['budget_usd'] = budget
        # weather / as_of
        near = w is not None
        start = s2d(case['start_date'])
        case['as_of'] = d2s(start - dt.timedelta(AS_OF_NEAR_DAYS if near else AS_OF_FAR_DAYS))
        days = trip_days(case['start_date'], case['end_date'])
        leads = {d: (s2d(d) - s2d(case['as_of'])).days for d in days}
        case['weather_fixture_needed'] = any(l <= HORIZON for l in leads.values())
        case['weather_fixture_files'] = ['data/weather/%s_%s.json' % (CITIES[city]['key'], d) for d in days if leads[d] <= HORIZON]
        case['weather_expected'] = {d: (WX[city][d]['flags'] or ['NONE']) if leads[d] <= HORIZON else ['OUT_OF_HORIZON'] for d in days}
        # free text for the places agent (gold tags stay the structured fields)
        txt = 'I would like ' + ', '.join(FREE_TEXT[t] for t in interests)
        if avoid: txt += '; ' + ', '.join(AVOID_TEXT.get(a, 'no ' + a) for a in avoid)
        if pace == 'relaxed': txt += '; no packed days'
        case['free_text'] = txt + '.'
        # oracle with the final budget
        if e_kind == 'car_over_4':
            orc = pk; orc['same_trip_without_car'] = best_package(dict(case, wants_car=False), budget)['status']
        else:
            orc = best_package(case, budget, count=True)
        if '_cheapest_any' in case: orc['cheapest_total_without_central'] = case.pop('_cheapest_any')
        if '_cheapest_no_car' in case: orc['cheapest_total_without_car'] = case.pop('_cheapest_no_car')
        if orc['status'] == 'FEASIBLE':
            orc['budget_slack_pct'] = round(100 * (budget - orc['cheapest_total']) / orc['cheapest_total'], 1)
            orc['share_combos_within_budget_pct'] = round(100 * orc['combos_within_budget'] / orc['combos_total'], 2)
        case['oracle_package'] = orc
        case['oracle_places'] = places_oracle(case)
        # expected status
        if grp == 'E':
            case['expected_status'] = orc['status']
            case['intended_conflict'] = True
            case['conflict_description'] = {'no_return_origin': 'origin %s has outbound flights to %s but no return records in the catalog' % (case['origin'], city),
                                            'budget_below_cheapest': 'budget below the cheapest package in the catalog',
                                            'car_over_4': '%d travelers with a car; capacity is only estimated, MVP limit is %d' % (Tn, MAX_CAR_TRAVELERS)}[e_kind]
            case['expected_reason'] = '; '.join(orc['reasons'])
        else:
            case['expected_status'] = 'OK_PLAN'
            case['intended_conflict'] = conflict is not None
            case['conflict_description'] = conflict or ''
            case['expected_reason'] = ''
        notes = []
        if city == 'New York': notes.append('NYC lodging in catalog for short stays is Jersey City/Newark (EWR mapping); NYC-market listings require >=30 nights')
        if car: notes.append('car capacity is an ESTIMATE by vehicle type (capacityEstimate), not verified seats')
        if case['oracle_places']['status'] == 'TO_BE_FILLED': notes.append('place-dependent checks to be filled when places data exists')
        elif case['oracle_places']['status'] == 'FAIL' and grp != 'E': notes.append('places oracle FAIL: review interests before freezing')
        case['notes'] = '; '.join(notes)
        cases.append(case)
    order = ['id','split','group','city','origin','start_date','end_date','travelers','budget_usd','wants_car','pace','interests','avoid',
             'hotel_preference','as_of','weather_fixture_needed','weather_fixture_files','weather_expected','free_text','intended_conflict',
             'conflict_description','expected_status','expected_reason','notes','oracle_package','oracle_places']
    cases = [{k: c[k] for k in order} for c in cases]
    meta = dict(built_with='build_eval_cases.py', seed=SEED, inventory=os.path.relpath(INV, TRAVEL),
                inventory_sha256='see verification_report.json (39a0c9c2...)', catalog_dates=[DATES[0], DATES[-1], len(DATES)],
                central_radius_km=CENTRAL_RADIUS_KM, city_centers={k: v['center_name'] for k, v in CITIES.items()},
                max_car_travelers=MAX_CAR_TRAVELERS, max_stay_km=MAX_STAY_KM, horizon_days=HORIZON, weather_thresholds=dict(rain_mm=RAIN_MM, rain_hours=RAIN_H, heat_c=HEAT_C, wind_kmh=WIND_KMH),
                weather_source='Open-Meteo Historical Forecast API, CC BY 4.0, retrieved 2026-10-21 (weather_preview/)',
                places_available={c: (c in PLACES) for c in CITIES}, vocab=VOCAB, slots_per_full_day=SLOTS, coverage_min=COVERAGE_MIN)
    json.dump(dict(meta=meta, cases=cases), open(os.path.join(HERE, 'eval_cases.json'), 'w'), ensure_ascii=False, indent=1)
    flat = ['id','split','group','city','origin','start_date','end_date','travelers','budget_usd','wants_car','pace','interests','avoid',
            'hotel_preference','as_of','weather_fixture_needed','intended_conflict','conflict_description','expected_status','expected_reason',
            'oracle_status','oracle_cheapest_total','budget_slack_pct','combos_within_budget','share_combos_within_budget_pct',
            'n_out_flights','n_back_flights','n_stays','n_cars','cheapest_stay_km_to_center','places_oracle','weather_flags','notes']
    with open(os.path.join(HERE, 'eval_cases.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        wr = csv.DictWriter(f, fieldnames=flat); wr.writeheader()
        for c in cases:
            o = c['oracle_package']
            wr.writerow(dict({k: c[k] for k in flat if k in c}, interests=';'.join(c['interests']), avoid=';'.join(c['avoid']),
                             oracle_status=o['status'], oracle_cheapest_total=o.get('cheapest_total', ''), budget_slack_pct=o.get('budget_slack_pct', ''),
                             combos_within_budget=o.get('combos_within_budget', ''), share_combos_within_budget_pct=o.get('share_combos_within_budget_pct', ''),
                             n_out_flights=o.get('n_out_flights', ''), n_back_flights=o.get('n_back_flights', ''), n_stays=o.get('n_stays', ''),
                             n_cars=o.get('n_cars', ''), cheapest_stay_km_to_center=(o.get('cheapest') or {}).get('stay_km_to_center', ''),
                             places_oracle=c['oracle_places']['status'],
                             weather_flags=' '.join('%s:%s' % (d[5:], '+'.join(v)) for d, v in c['weather_expected'].items())))
    # summary
    cnt = Counter((c['split'], c['group'], c['city']) for c in cases)
    for k in sorted(cnt): print(k, cnt[k])
    for c in cases:
        o = c['oracle_package']
        print(c['id'], c['city'][:3], c['origin'], c['start_date'], c['end_date'], 'T=%d' % c['travelers'], 'car' if c['wants_car'] else '-', c['hotel_preference'],
              '$%d' % c['budget_usd'], o['status'], o.get('cheapest_total'), o.get('budget_slack_pct'), o.get('combos_within_budget'),
              c['oracle_places']['status'], c['expected_status'])

if __name__ == '__main__':
    main()
