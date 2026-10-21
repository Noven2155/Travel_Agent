# Frozen eval set

`eval_cases.json` (40 eval + 8 dev cases, Chicago + New York, with oracle results) was copied unchanged from
`system_definition/` on 2026-10-21 and is frozen **before the first run of system B or C** (spec 6.4, rule 1).

    sha256(eval_cases.json) = f2bd63d99d8fd3c6958a081d2513e84bd31095890489e1fe55c731670b6a6fdc

Verify: `cd eval/cases && sha256sum -c FROZEN.sha256`. `python -m eval.run_eval` records the hash in every
`run_meta.json` (`frozen_ok`). Any change to the cases or thresholds requires a new version and a re-run of all
three systems. Prompts and thresholds are tuned only on the 8 dev cases (V01–V08).

- `build_eval_cases.py` – the deterministic generator (seed 20261030). It reads `inventory.json`,
  the Open-Meteo weather preview and the places CSVs from the original `/workspace/travel` layout
  (paths at the top of the script); kept here for provenance, not needed to run the eval.
- `eval_cases.csv` – one row per case (UTF-8 with BOM, for Excel).
- New York `oracle_places` is `TO_BE_FILLED` until `data/places/nyc_places.csv` exists.
