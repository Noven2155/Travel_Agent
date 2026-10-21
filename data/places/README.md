# Places data (`data/places/`)

| file | content |
|---|---|
| `chicago_places.csv` | 579 places in Chicago (restaurants, cafes, bars, museums, theatres, parks, attractions…) |
| `nyc_places.csv` | 616 places in New York City (same columns). Attractions from all 5 boroughs; **food only from Manhattan** (Manhattan south of lat 40.781 + NW quadrant). NE Manhattan (East Harlem / north UES) and all Brooklyn food tiles could not be fetched (repeated Overpass 502/504/timeouts) and are missing. |
| `build_places.py` | the script that built both files (OpenStreetMap Overpass + Wikivoyage), kept for provenance; `--offline` rebuilds from its raw cache |

Sources and licenses
- **OpenStreetMap** (names, categories, coordinates, opening_hours, website, address): © OpenStreetMap contributors, **ODbL 1.0** – https://www.openstreetmap.org/copyright
- **Wikivoyage** (`in_wikivoyage`, `description_short` where `description_source` says so): **CC BY-SA 4.0** – https://en.wikivoyage.org
- Retrieved 2026-10-21 (`retrieved_at` column).

**Synthetic fields** (listed per row in `synthetic_fields`, generated with seed 42 for demo purposes only):
`rating`, `review_count`, `typical_visit_minutes` and most `price_level` values (`price_source=synthetic`).
The tools never return `rating`/`review_count`/`price_level`; `typical_visit_minutes` is returned only as an
explicit *estimate* (`typical_visit_minutes_basis="estimate"`) to size visits. None of these fields is used for
ranking or for the grounding check, and the grounding check fails if any of them appears in a plan.
`indoor` is derived in code from the OSM category (`unknown` is treated as outdoor on rain days).
