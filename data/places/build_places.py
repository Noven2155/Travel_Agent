#!/usr/bin/env python3
"""
build_places.py - reproducible builder for a free, legally clean places dataset
(attractions + food) for Chicago and New York City.

Sources (free, keyless):
  * OpenStreetMap via public Overpass API mirrors  (ODbL, "© OpenStreetMap contributors")
  * Wikivoyage via the MediaWiki API                (CC BY-SA 4.0)

All raw responses are cached under raw/ ; a rerun uses the cache (offline).
Use --refresh to re-download.  Synthetic fields use a fixed seed (SEED=42).

Usage:  python3 build_places.py [--refresh]
"""
import csv, hashlib, json, math, os, random, re, sys, time
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
os.makedirs(RAW, exist_ok=True)
REFRESH = "--refresh" in sys.argv
SEED = 42
UA = "StudentTravelPlannerDataset/1.0 (educational CrewAI class project; low-volume, cached)"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
WV_API = "https://en.wikivoyage.org/w/api.php"

TARGET_ATTR = 220   # per city
TARGET_FOOD = 330   # per city  (=> ~550 total, ~40/60)

CITIES = {
    "chicago": {
        "label": "Chicago", "rel": 122604,
        # one "sub-area" = the whole city
        "subareas": [("Chicago", None)],
        "food_subareas": [("Chicago", None)],
        "wv_prefixes": ["Chicago/"], "wv_pages": ["Chicago"],
    },
    "nyc": {
        "label": "New York City", "rel": 175905,
        "subareas": [("Manhattan", "^Manhattan$"), ("Brooklyn", "^Brooklyn$"),
                     ("Queens", "^Queens$"), ("Bronx", "^(The Bronx|Bronx)$"),
                     ("Staten Island", "^Staten Island$")],
        "optional_subareas": ["Bronx", "Staten Island"],
        "target_attr": 240, "target_food": 360,
        # food limited to Manhattan + Brooklyn to keep downloads modest
        "food_subareas": [("Manhattan", "^Manhattan$"), ("Brooklyn", "^Brooklyn$")],
        "wv_prefixes": ["Manhattan/", "Brooklyn/", "Queens/", "The Bronx/", "Staten Island/"],
        "wv_pages": ["New York City", "Manhattan", "Brooklyn", "Queens", "The Bronx", "Staten Island"],
    },
}

LOG = []
def log(msg):
    print(msg, flush=True); LOG.append(msg)

# ----------------------------------------------------------------------------- HTTP
def overpass(query, cache_name, attempts=8, optional=False):
    path = os.path.join(RAW, cache_name)
    if os.path.exists(path) and not REFRESH:
        with open(path) as f:
            return json.load(f)
    last = None
    for attempt in range(attempts):
        for ep in OVERPASS_ENDPOINTS:
            try:
                r = requests.post(ep, data={"data": query}, headers={"User-Agent": UA}, timeout=200)
                if r.status_code == 200:
                    d = r.json()
                    if "remark" in d and "error" in d["remark"].lower():
                        raise RuntimeError("Overpass remark: " + d["remark"][:200])
                    d["_retrieved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    d["_endpoint"] = ep
                    with open(path, "w") as f:
                        json.dump(d, f)
                    log(f"  fetched {cache_name} from {ep}: {len(d['elements'])} elements")
                    return d
                last = f"HTTP {r.status_code} from {ep}"
            except Exception as e:  # network / TLS / JSON errors
                last = f"{type(e).__name__} from {ep}: {str(e)[:120]}"
            log(f"  retry ({cache_name}): {last}")
            time.sleep(3)
        wait = min(20 * 2 ** attempt, 240)
        log(f"  all endpoints failed for {cache_name}, backing off {wait}s")
        time.sleep(wait)
    if optional:
        log(f"  GIVING UP on optional {cache_name} after {attempts} rounds: {last}")
        return None
    raise RuntimeError(f"Overpass failed for {cache_name}: {last}")

def wv_get(params, cache_name):
    path = os.path.join(RAW, cache_name)
    if os.path.exists(path) and not REFRESH:
        with open(path) as f:
            return json.load(f)
    params = dict(params, format="json", formatversion=2)
    for attempt in range(6):
        try:
            r = requests.get(WV_API, params=params, headers={"User-Agent": UA}, timeout=60)
            if r.status_code == 200:
                d = r.json()
                with open(path, "w") as f:
                    json.dump(d, f)
                time.sleep(0.5)
                return d
            log(f"  wikivoyage HTTP {r.status_code}")
        except Exception as e:
            log(f"  wikivoyage error {type(e).__name__}: {str(e)[:100]}")
        time.sleep(5 * 2 ** attempt)
    raise RuntimeError("Wikivoyage failed: " + cache_name)

# ----------------------------------------------------------------------------- OSM queries
def area_prefix(cfg, name_re):
    a = f"area({3600000000 + cfg['rel']})->.city;"
    if name_re is None:
        return a + "(.city;)->.sa;"
    return (a + f'rel(area.city)["boundary"="administrative"]["name"~"{name_re}"]->.r;'
            ".r map_to_area->.sa;")

ATTR_BODY = """(
  nwr(area.sa)["tourism"~"^(attraction|museum|gallery|viewpoint|zoo|aquarium|theme_park)$"]["name"];
  nwr(area.sa)["amenity"~"^(theatre|arts_centre|marketplace)$"]["name"];
  nwr(area.sa)["shop"="mall"]["name"];
  nwr(area.sa)["leisure"="park"]["name"]["wikidata"];
  nwr(area.sa)["historic"]["name"]["wikidata"];
  nwr(area.sa)["leisure"~"^(water_park|ice_rink|escape_game|trampoline_park)$"]["name"];
  nwr(area.sa)["sport"="climbing"]["name"];
);
out center tags;"""
FOOD_BODY = """nwr(area.sa)["amenity"~"^(restaurant|cafe|fast_food|food_court|bar|pub)$"]["name"];
out center tags;"""
PLACE_BODY = 'node(area.city)["place"~"^(neighbourhood|suburb|quarter)$"]["name"];out;'

FOOD_TILE_BODY = """nwr(area.sa)({s},{w},{n},{e})["amenity"~"^(restaurant|cafe|fast_food|food_court|bar|pub)$"]["name"];
out center tags;"""

def borough_area_ids(ckey, cfg):
    """Cheap lookup of borough relation ids -> Overpass area ids (avoids map_to_area)."""
    rx = "|".join(r.strip("^$") for _, r in cfg["subareas"])
    d = overpass(f'[out:json][timeout:180];area({3600000000 + cfg["rel"]})->.city;'
                 f'rel(area.city)["boundary"="administrative"]["name"~"^({rx})$"];out tags;',
                 f"{ckey}_borough_ids.json")
    ids = {}
    for e in d["elements"]:
        nm = e["tags"].get("name"); al = e["tags"].get("admin_level", "")
        if nm and (nm not in ids or al == "5"):
            ids[nm] = 3600000000 + e["id"]
    return ids

def tiles(b, nx=2, ny=2):
    out = []
    for i in range(ny):
        for j in range(nx):
            s_ = b["minlat"] + (b["maxlat"] - b["minlat"]) * i / ny
            n_ = b["minlat"] + (b["maxlat"] - b["minlat"]) * (i + 1) / ny
            w_ = b["minlon"] + (b["maxlon"] - b["minlon"]) * j / nx
            e_ = b["minlon"] + (b["maxlon"] - b["minlon"]) * (j + 1) / nx
            out.append((round(s_, 5), round(w_, 5), round(n_, 5), round(e_, 5)))
    return out

def fetch_osm(ckey, cfg):
    hdr = "[out:json][timeout:180];"
    bounds = overpass(hdr + f"rel({cfg['rel']});out bb;", f"{ckey}_boundary.json")
    b = bounds["elements"][0]["bounds"]
    places = overpass(hdr + area_prefix(cfg, None) + PLACE_BODY, f"{ckey}_places.json")
    groups, skipped = [], []
    opt = cfg.get("optional_subareas", [])
    for sub, rx in cfg["subareas"]:
        slug = sub.lower().replace(" ", "_")
        d = overpass(hdr + area_prefix(cfg, rx) + ATTR_BODY, f"{ckey}_{slug}_attractions.json",
                     attempts=3 if sub in opt else 8, optional=sub in opt)
        if d is None: skipped.append(sub); continue
        groups.append(("attraction", sub, d))
    if rx_none(cfg["food_subareas"]):
        groups.append(("food", cfg["label"], overpass(hdr + area_prefix(cfg, None) + FOOD_BODY,
                                                      f"{ckey}_{ckey}_food.json")))
    else:
        # NYC: per borough, split into 2x2 bbox tiles, using precomputed borough areas
        ids = borough_area_ids(ckey, cfg)
        bb = overpass(hdr + "(" + "".join(f"rel({a - 3600000000});" for nm, a in ids.items()) + ");out bb tags;",
                      f"{ckey}_borough_bounds.json")
        bbs = {e["tags"]["name"]: e["bounds"] for e in bb["elements"]}
        for sub, rx in cfg["food_subareas"]:
            nm = next(k for k in ids if re.match(rx, k))
            slug = sub.lower().replace(" ", "_")
            for ti, (s_, w_, n_, e_) in enumerate(tiles(bbs[nm])):
                q = (hdr + f"area({ids[nm]})->.sa;" +
                     FOOD_TILE_BODY.format(s=s_, w=w_, n=n_, e=e_))
                groups.append(("food", sub, overpass(q, f"{ckey}_{slug}_food_tile{ti}.json")))
                time.sleep(5)
    return b, places, groups, skipped

def rx_none(subs):
    return len(subs) == 1 and subs[0][1] is None

# ----------------------------------------------------------------------------- Wikivoyage
LISTING_TYPES = {"see": "see", "do": "do", "eat": "eat", "drink": "drink", "buy": "buy", "listing": "listing"}

def extract_templates(text):
    """Yield raw '{{...}}' top-level template strings."""
    i, n = 0, len(text)
    while i < n:
        j = text.find("{{", i)
        if j < 0: return
        depth, k = 0, j
        while k < n - 1:
            if text[k:k+2] == "{{": depth += 1; k += 2; continue
            if text[k:k+2] == "}}":
                depth -= 1; k += 2
                if depth == 0: break
                continue
            k += 1
        yield j, text[j:k]
        i = k

def split_params(body):
    parts, cur, d1, d2 = [], [], 0, 0
    i = 0
    while i < len(body):
        two = body[i:i+2]
        if two == "{{": d1 += 1; cur.append(two); i += 2; continue
        if two == "}}": d1 -= 1; cur.append(two); i += 2; continue
        if two == "[[": d2 += 1; cur.append(two); i += 2; continue
        if two == "]]": d2 -= 1; cur.append(two); i += 2; continue
        if body[i] == "|" and d1 == 0 and d2 == 0:
            parts.append("".join(cur)); cur = []; i += 1; continue
        cur.append(body[i]); i += 1
    parts.append("".join(cur))
    return parts

def clean_wikitext(s):
    s = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    for _ in range(3):
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", s)
    s = re.sub(r"\[https?://\S+\]", "", s)
    s = s.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", s).strip()

def parse_listings(title, text):
    out = []
    heads = [(m.start(), m.group(1).strip().lower()) for m in re.finditer(r"^=+\s*([^=]+?)\s*=+\s*$", text, re.M)]
    for pos, t in extract_templates(text):
        sect = ""
        for hp, hn in heads:
            if hp < pos: sect = hn
            else: break
        tier = {"budget": 1, "cheap": 1, "mid-range": 2, "mid range": 2, "midrange": 2,
                "splurge": 3, "expensive": 3}.get(sect)
        parts = split_params(t[2:-2])
        ttype = parts[0].strip().lower()
        if ttype not in LISTING_TYPES: continue
        p = {}
        for x in parts[1:]:
            if "=" in x:
                k, v = x.split("=", 1); p[k.strip().lower()] = v.strip()
        if ttype == "listing":
            ttype = p.get("type", "listing").lower()
            if ttype not in LISTING_TYPES: continue
        name = clean_wikitext(p.get("name", ""))
        if not name: continue
        def fnum(v):
            try: return float(v)
            except: return None
        out.append({"page": title, "type": ttype, "name": name,
                    "alt": clean_wikitext(p.get("alt", "")),
                    "wikidata": p.get("wikidata", "").strip(),
                    "lat": fnum(p.get("lat", "")), "lon": fnum(p.get("long", "")),
                    "content": clean_wikitext(p.get("content", "") or p.get("description", "")),
                    "price_tier": tier if ttype in ("eat", "drink") else None})
    return out

def fetch_wikivoyage(ckey, cfg):
    titles = list(cfg["wv_pages"])
    for pre in cfg["wv_prefixes"]:
        cont, n = {}, 0
        while True:
            d = wv_get(dict(action="query", list="allpages", apprefix=pre, aplimit=500,
                            apfilterredir="nonredirects", **cont),
                       f"wv_{ckey}_allpages_{pre.strip('/').replace(' ', '_')}_{n}.json")
            titles += [p["title"] for p in d["query"]["allpages"]]
            if "continue" not in d: break
            cont = {"apcontinue": d["continue"]["apcontinue"]}; n += 1
    titles = sorted(set(titles))
    listings, pages = [], []
    for i in range(0, len(titles), 40):
        batch = titles[i:i+40]
        d = wv_get(dict(action="query", prop="revisions", rvprop="content", rvslots="main",
                        titles="|".join(batch)), f"wv_{ckey}_content_{i//40:03d}.json")
        for pg in d["query"]["pages"]:
            if "revisions" not in pg: continue
            txt = pg["revisions"][0]["slots"]["main"]["content"]
            pages.append(pg["title"])
            listings += parse_listings(pg["title"], txt)
    return pages, listings

# ----------------------------------------------------------------------------- helpers
def norm_name(s):
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[’'`\.]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"^(the )", "", s.strip())
    return s.strip()

def hav_km(a, b, c, d):
    R = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dl, dp = math.radians(d - b), p2 - p1
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(h))

def rng_for(pid):
    h = int(hashlib.sha256(f"{SEED}:{pid}".encode()).hexdigest()[:16], 16)
    return random.Random(h)

def classify(t, group):
    tour, am, le, hi, sh = (t.get("tourism"), t.get("amenity"), t.get("leisure"),
                            t.get("historic"), t.get("shop"))
    if group == "food":
        if am == "pub": return "bar", "pub"
        sub = (t.get("cuisine") or "").replace(";", ", ").replace("_", " ")
        return am, sub
    if tour in ("zoo", "aquarium", "theme_park", "museum", "gallery"):
        return tour, (t.get("museum") or t.get("zoo") or t.get("artwork_type") or "")
    if am in ("theatre", "arts_centre"):
        return am, (t.get("theatre:genre") or "")
    if sh == "mall": return "shopping", "mall"
    if am == "marketplace": return "shopping", "market"
    if le in ("water_park", "ice_rink", "escape_game", "trampoline_park") or t.get("sport") == "climbing":
        return "activity", (le or "climbing").replace("_", " ")
    if tour == "viewpoint": return "viewpoint", ""
    if le == "park": return "park", ""
    if hi: return "historic", hi.replace("_", " ")
    if tour == "attraction": return "attraction", (t.get("attraction") or "")
    return "attraction", ""

ADV_RE = re.compile(r"\b(climb\w*|kayak\w*|zip ?line|skydeck|tilt|ledge|edge|ropes?|adventure|boulder\w*|trampoline|escape|go[- ]?kart|skate\w*|surf\w*|thrill)\b", re.I)

def interest_tags(cat, sub, t, name):
    tags = set()
    m = {
        "museum": ["culture", "attractions", "family"], "gallery": ["culture"],
        "theatre": ["shows", "culture", "nightlife"], "arts_centre": ["culture", "shows"],
        "zoo": ["family", "nature", "attractions"], "aquarium": ["family", "nature", "attractions"],
        "theme_park": ["family", "extreme/adventure", "attractions"],
        "park": ["nature", "family"], "viewpoint": ["attractions", "nature"],
        "attraction": ["attractions"], "historic": ["culture", "attractions"],
        "shopping": ["shopping"], "activity": ["extreme/adventure", "family"],
        "restaurant": ["food"], "cafe": ["food"], "fast_food": ["food"], "food_court": ["food"],
        "bar": ["nightlife", "food"],
    }
    tags.update(m.get(cat, []))
    if cat == "shopping" and sub == "market": tags.add("food")
    if cat == "museum" and t.get("museum") in ("art",): tags.discard("family")
    if t.get("attraction") in ("roller_coaster", "amusement_ride") : tags.add("extreme/adventure")
    if ADV_RE.search(name) and cat not in ("restaurant", "cafe", "fast_food", "bar", "food_court"):
        tags.add("extreme/adventure")
    if cat in ("restaurant", "cafe", "fast_food") and t.get("diet:kids") == "yes": tags.add("family")
    if t.get("natural") or t.get("garden:type") or "garden" in name.lower() or "beach" in name.lower():
        if cat not in ("restaurant", "cafe", "fast_food", "bar"): tags.add("nature")
    order = ["attractions", "shows", "nature", "extreme/adventure", "shopping", "culture", "food", "nightlife", "family"]
    return [x for x in order if x in tags]

INDOOR = {"museum": "true", "gallery": "true", "theatre": "true", "arts_centre": "true",
          "aquarium": "true", "restaurant": "true", "cafe": "true", "fast_food": "true",
          "food_court": "true", "bar": "true", "park": "false", "viewpoint": "false",
          "zoo": "false", "theme_park": "false", "attraction": "unknown",
          "historic": "unknown", "activity": "unknown"}
def indoor_rule(cat, sub, t):
    if t.get("indoor") in ("yes", "no"): return "true" if t["indoor"] == "yes" else "false"
    if cat == "shopping": return "true" if sub == "mall" else "unknown"
    if cat == "historic" and sub in ("monument", "memorial", "ship", "milestone", "boundary stone"):
        return "false"
    if cat == "activity": return {"escape game": "true", "trampoline park": "true",
                                  "water park": "false"}.get(sub, "unknown")
    return INDOOR.get(cat, "unknown")

VISIT_MIN = {"museum": 120, "gallery": 60, "zoo": 180, "aquarium": 150, "theme_park": 240,
             "park": 75, "viewpoint": 30, "attraction": 60, "historic": 30, "theatre": 150,
             "arts_centre": 90, "shopping": 75, "activity": 90, "restaurant": 75, "cafe": 30,
             "fast_food": 20, "food_court": 40, "bar": 90}
PRICE_PRIOR = {"museum": 2.4, "gallery": 1.4, "zoo": 2.0, "aquarium": 3.0, "theme_park": 3.2,
               "park": 1.0, "viewpoint": 1.3, "attraction": 1.8, "historic": 1.2, "theatre": 3.0,
               "arts_centre": 2.0, "shopping": 2.2, "activity": 2.5, "restaurant": 2.2,
               "cafe": 1.4, "fast_food": 1.0, "food_court": 1.2, "bar": 2.0}
PRICEY = ("steak", "french", "sushi", "japanese", "seafood", "fine_dining", "omakase", "italian")
CHEAP = ("pizza", "burger", "mexican", "taco", "sandwich", "hot_dog", "bagel", "chicken", "donut", "ice_cream", "coffee_shop")

def synth(row, t, rng):
    syn = []
    cat = row["category"]
    # typical visit minutes (always synthetic)
    base = VISIT_MIN.get(cat, 60)
    row["typical_visit_minutes"] = max(10, int(round(base * rng.uniform(0.8, 1.25) / 5) * 5))
    syn.append("typical_visit_minutes")
    # price level: OSM hint fee=no -> 1 (derived, not synthetic)
    if t.get("fee") == "no" and row["group"] == "attraction":
        row["price_level"] = 1
        row["price_source"] = "OSM fee=no"
    elif row.get("_wv_tier"):
        row["price_level"] = row["_wv_tier"]
        row["price_source"] = "Wikivoyage section (Budget/Mid-range/Splurge)"
    else:
        p = PRICE_PRIOR.get(cat, 2.0)
        cu = (t.get("cuisine") or "").lower()
        if any(k in cu for k in PRICEY): p += 0.8
        if any(k in cu for k in CHEAP): p -= 0.7
        if t.get("fee") == "yes": p += 0.5
        row["price_level"] = int(min(4, max(1, round(p + rng.gauss(0, 0.55)))))
        row["price_source"] = "synthetic"
        syn.append("price_level")
    # rating / review_count (always synthetic)
    fame = (0.25 if row["in_wikivoyage"] else 0) + (0.12 if row["wikidata"] else 0)
    row["rating"] = round(min(5.0, max(1.0, rng.gauss(4.05 + fame, 0.33))), 1)
    row["rating"] = min(row["rating"], 4.9)
    mu = 4.3 + (1.6 if row["in_wikivoyage"] else 0) + (1.0 if row["wikidata"] else 0) \
        + (0.6 if cat in ("museum", "zoo", "aquarium", "theme_park") else 0)
    row["review_count"] = int(max(3, round(rng.lognormvariate(mu, 0.9))))
    syn += ["rating", "review_count"]
    row["synthetic_fields"] = syn

def osm_description(cat, sub, hood, t):
    labels = {"museum": "Museum", "gallery": "Art gallery", "zoo": "Zoo", "aquarium": "Aquarium",
              "theme_park": "Amusement park", "park": "Park", "viewpoint": "Scenic viewpoint",
              "attraction": "Tourist attraction", "historic": "Historic site", "theatre": "Theatre",
              "arts_centre": "Arts centre", "shopping": "Shopping", "activity": "Activity venue",
              "restaurant": "Restaurant", "cafe": "Café", "fast_food": "Fast-food spot",
              "food_court": "Food court", "bar": "Bar"}
    lab = labels.get(cat, cat.title())
    if cat == "shopping": lab = "Shopping mall" if sub == "mall" else "Market"
    elif cat == "bar" and sub == "pub": lab = "Pub"
    elif cat == "historic" and sub: lab = f"Historic {sub}"
    elif cat == "museum" and sub: lab = f"{sub.replace('_', ' ').capitalize()} museum"
    elif cat == "activity" and sub: lab = sub.capitalize()
    elif cat in ("restaurant", "cafe", "fast_food") and sub:
        c = ", ".join(x.strip().replace("_", " ") for x in sub.split(",")[:2])
        lab = f"{lab} ({c})"
    s = lab + (f" in {hood}" if hood else "")
    extras = []
    if t.get("outdoor_seating") == "yes": extras.append("outdoor seating")
    if t.get("wheelchair") == "yes": extras.append("wheelchair accessible")
    if t.get("fee") == "no" and cat not in ("restaurant", "cafe", "fast_food", "bar"): extras.append("free entry")
    if extras: s += "; " + ", ".join(extras)
    return s + "."

def short(text, n=180):
    text = text.strip()
    if len(text) <= n: return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"

# ----------------------------------------------------------------------------- build
def build_city(ckey, cfg):
    log(f"== {cfg['label']}")
    bounds, places, groups, skipped = fetch_osm(ckey, cfg)
    if skipped: log(f"  skipped (Overpass failures): {skipped}")
    try:
        wv_pages, wv = fetch_wikivoyage(ckey, cfg)
        wv = [l for l in wv if l["type"] != "sleep"]
    except Exception as e:
        log(f"  Wikivoyage unavailable ({e}); continuing without it"); wv_pages, wv = [], []
    log(f"  Wikivoyage: {len(wv_pages)} pages, {len(wv)} see/do/eat/drink/buy listings")
    retrieved = {}
    for f in os.listdir(RAW):
        if f.startswith(ckey + "_"):
            with open(os.path.join(RAW, f)) as fh:
                retrieved[f] = json.load(fh).get("_retrieved_at", "")
    retrieved_at = max(v for v in retrieved.values() if v)[:10]

    hoods = [(e["lat"], e["lon"], e["tags"]["name"]) for e in places["elements"] if "lat" in e]

    # candidates
    cands = {}
    for group, sub, data in groups:
        for e in data["elements"]:
            t = e.get("tags", {})
            name = (t.get("name") or "").strip()
            if not name: continue
            lat = e.get("lat", e.get("center", {}).get("lat"))
            lon = e.get("lon", e.get("center", {}).get("lon"))
            if lat is None: continue
            pid = f"osm:{e['type']}/{e['id']}"
            if pid in cands: continue
            cands[pid] = dict(pid=pid, e=e, t=t, name=name, lat=lat, lon=lon, group=group, borough=sub)
    # parks/historic without wikidata are already excluded in the query (notability proxy)

    # wikivoyage matching
    by_wd, by_name = {}, {}
    for c in cands.values():
        if c["t"].get("wikidata"): by_wd.setdefault(c["t"]["wikidata"], []).append(c)
        by_name.setdefault(norm_name(c["name"]), []).append(c)
    n_match = 0
    for l in wv:
        hits = []
        if l["wikidata"] and l["wikidata"] in by_wd:
            hits = by_wd[l["wikidata"]]
        else:
            for nm in (l["name"], l["alt"]):
                if not nm: continue
                cs = by_name.get(norm_name(nm), [])
                if l["lat"] is not None and l["lon"] is not None:
                    cs = [c for c in cs if hav_km(l["lat"], l["lon"], c["lat"], c["lon"]) < 1.0]
                elif len(cs) > 1:
                    cs = []   # ambiguous (e.g. chains) -> no match
                if cs: hits = cs; break
        if hits:
            n_match += 1
            for c in hits:
                if "wv" not in c or (not c["wv"]["content"] and l["content"]):
                    c["wv"] = l
    log(f"  Wikivoyage listings matched to OSM: {n_match}")

    # score + dedupe same-name near-duplicates
    def score(c):
        t = c["t"]
        s = sum(1 for k in ("website", "contact:website", "opening_hours", "cuisine", "wikidata",
                            "wikipedia", "phone", "contact:phone", "addr:street", "addr:housenumber")
                if t.get(k))
        s += 0.05 * min(len(t), 40) + (3 if t.get("wikidata") else 0) + (20 if "wv" in c else 0)
        return s + rng_for(c["pid"]).random() * 0.5
    for c in cands.values():
        c["score"] = score(c)
        c["cat"], c["sub"] = classify(c["t"], c["group"])
    pool = sorted(cands.values(), key=lambda c: -c["score"])
    kept, seen = [], {}
    for c in pool:
        k = norm_name(c["name"])
        if any(hav_km(c["lat"], c["lon"], o["lat"], o["lon"]) < 0.15 for o in seen.get(k, [])):
            continue
        seen.setdefault(k, []).append(c); kept.append(c)

    # select with quotas
    def pick(items, target, quotas):
        chosen, ids = [], set()
        wvs = [c for c in items if "wv" in c]
        cap_wv = int(target * 0.75)  # keep room for diversity
        for c in wvs[:cap_wv]:
            chosen.append(c); ids.add(c["pid"])
        for cat, share in quotas.items():
            have = sum(1 for c in chosen if c["cat"] == cat)
            need = int(round(target * share)) - have
            for c in items:
                if need <= 0: break
                if c["cat"] == cat and c["pid"] not in ids:
                    chosen.append(c); ids.add(c["pid"]); need -= 1
        for c in items:
            if len(chosen) >= target: break
            if c["pid"] not in ids:
                chosen.append(c); ids.add(c["pid"])
        return chosen
    attr = [c for c in kept if c["group"] == "attraction"]
    food = [c for c in kept if c["group"] == "food"]
    sel = pick(attr, cfg.get("target_attr", TARGET_ATTR), {"museum": .16, "park": .14, "attraction": .13, "historic": .10,
                                   "theatre": .09, "gallery": .07, "viewpoint": .05, "shopping": .06,
                                   "arts_centre": .04, "activity": .05, "zoo": .01, "aquarium": .01,
                                   "theme_park": .01})
    sel += pick(food, cfg.get("target_food", TARGET_FOOD), {"restaurant": .58, "cafe": .18, "bar": .12, "fast_food": .09,
                                    "food_court": .03})

    rows = []
    for c in sel:
        t, e = c["t"], c["e"]
        hood = ""
        best = 2.0
        for la, lo, nm in hoods:
            if abs(la - c["lat"]) > 0.03 or abs(lo - c["lon"]) > 0.04: continue
            d = hav_km(c["lat"], c["lon"], la, lo)
            if d < best: best, hood = d, nm
        if ckey == "nyc":
            hood = f"{hood}, {c['borough']}" if hood and hood != c["borough"] else c["borough"]
        addr = " ".join(x for x in (t.get("addr:housenumber", ""), t.get("addr:street", "")) if x)
        tail = ", ".join(x for x in (t.get("addr:city", ""), t.get("addr:postcode", "")) if x)
        addr = ", ".join(x for x in (addr, tail) if x)
        wvl = c.get("wv")
        if wvl and wvl["content"]:
            desc, dsrc = short(wvl["content"]), f"Wikivoyage: {wvl['page']} (CC BY-SA 4.0)"
        else:
            desc, dsrc = osm_description(c["cat"], c["sub"], hood.split(",")[0], t), "generated from OSM tags"
        row = dict(
            place_id=c["pid"], city=cfg["label"], name=c["name"], category=c["cat"],
            subcategory=c["sub"], tags=interest_tags(c["cat"], c["sub"], t, c["name"]),
            indoor=indoor_rule(c["cat"], c["sub"], t), lat=round(c["lat"], 7), lon=round(c["lon"], 7),
            neighborhood=hood, address=addr, opening_hours=t.get("opening_hours", ""),
            website=t.get("website") or t.get("contact:website") or "",
            wikidata=t.get("wikidata", ""), in_wikivoyage=bool(wvl),
            description_short=desc, description_source=dsrc,
            typical_visit_minutes=None, price_level=None, rating=None, review_count=None,
            source="OSM+Wikivoyage" if wvl else "OSM",
            source_url=f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
            license="ODbL 1.0 (© OpenStreetMap contributors)" +
                    ("; description_short CC BY-SA 4.0 (Wikivoyage contributors)" if wvl and wvl["content"] else ""),
            retrieved_at=retrieved_at, group=c["group"], synthetic_fields=[],
            _wv_tier=(wvl or {}).get("price_tier"))
        synth(row, t, rng_for(row["place_id"]))
        rows.append(row)
    rows.sort(key=lambda r: (r["group"], r["category"], r["name"]))
    return rows, bounds, dict(wv_pages=len(wv_pages), wv_listings=len(wv), wv_matched=n_match,
                              candidates=len(cands), skipped_subareas=skipped)

FIELDS = ["place_id", "city", "name", "category", "subcategory", "tags", "indoor", "lat", "lon",
          "neighborhood", "address", "opening_hours", "website", "wikidata", "in_wikivoyage",
          "description_short", "description_source", "typical_visit_minutes", "price_level", "price_source",
          "rating", "review_count", "source", "source_url", "license", "retrieved_at",
          "synthetic_fields"]

def qa(rows, bounds, label):
    ids = [r["place_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate place_id"
    assert all(r["name"].strip() for r in rows), "empty name"
    for r in rows:
        assert bounds["minlat"] <= r["lat"] <= bounds["maxlat"] and bounds["minlon"] <= r["lon"] <= bounds["maxlon"], r["place_id"]
        assert r["synthetic_fields"], "synthetic_fields empty: " + r["place_id"]
        assert 1.0 <= r["rating"] <= 5.0 and 1 <= r["price_level"] <= 4
    n = len(rows)
    pct = lambda f: round(100 * sum(1 for r in rows if r[f]) / n, 1)
    cats = {}
    for r in rows: cats[r["category"]] = cats.get(r["category"], 0) + 1
    tagc = {}
    for r in rows:
        for t in r["tags"]: tagc[t] = tagc.get(t, 0) + 1
    st = dict(city=label, total=n, attractions=sum(r["group"] == "attraction" for r in rows),
              food=sum(r["group"] == "food" for r in rows),
              categories=dict(sorted(cats.items(), key=lambda x: -x[1])),
              interest_tags=dict(sorted(tagc.items(), key=lambda x: -x[1])),
              coverage_pct={f: pct(f) for f in ("opening_hours", "website", "wikidata", "in_wikivoyage", "address", "neighborhood")},
              indoor={v: sum(r["indoor"] == v for r in rows) for v in ("true", "false", "unknown")},
              price_level_real_hint=sum("price_level" not in r["synthetic_fields"] for r in rows),
              synthetic_fields_populated=all(r["synthetic_fields"] for r in rows),
              checks="OK: unique place_id, no empty names, all lat/lon inside city boundary bbox")
    return st

def write(rows, ckey):
    with open(os.path.join(HERE, f"{ckey}_places.json"), "w", encoding="utf-8") as f:
        json.dump([{k: r[k] for k in FIELDS} for r in rows], f, ensure_ascii=False, indent=1)
    with open(os.path.join(HERE, f"{ckey}_places.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            d = {k: r[k] for k in FIELDS}
            d["tags"] = ";".join(r["tags"]); d["synthetic_fields"] = ";".join(r["synthetic_fields"])
            d["in_wikivoyage"] = str(r["in_wikivoyage"]).lower()
            w.writerow(d)

def main():
    stats = {}
    for ckey, cfg in CITIES.items():
        rows, bounds, extra = build_city(ckey, cfg)
        st = qa(rows, bounds, cfg["label"]); st.update(extra); st["bbox"] = bounds
        stats[ckey] = st
        write(rows, ckey)
        log(json.dumps(st, ensure_ascii=False))
    with open(os.path.join(HERE, "build_stats.json"), "w") as f:
        json.dump(stats, f, indent=1, ensure_ascii=False)

if __name__ == "__main__":
    main()
