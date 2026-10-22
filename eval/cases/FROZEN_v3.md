# eval_cases_v3.json - frozen 2026-10-21 (free-text segment, additive)

sha256: see `FROZEN_v3.sha256`. v1 (`eval_cases.json`) and v2 (`eval_cases_v2.json`) are unchanged.

* 24 cases (group F, segment `free_text`): 20 eval (Chicago 10, New York 10; direct 10, indirect 10) + 4 dev (G01-G04).
* Systems see ONLY `id`, `request_text` and `as_of`. `gold.request` (the structured fields the text implies) and
  `gold.key_requirements` (2-3 per case: checker id + params, scored by `eval/keyreq.py`) are hidden.
* Built by `build_eval_cases_v3.py` from `v3_specs.py` (hand-written texts) on the densest (origin, window) combinations,
  with the v2 oracle: >= 10 feasible packages under the gold hard constraints, places oracle PASS, binding flight-time /
  priority requirements, and the pipeline's package count equal to the oracle's.
* Keyword parser (System A on free text) and strong-rules handling of the new fields were tuned on the 4 dev cases only.
  The texts and the parser were written by the same author (an agent) before the eval run; the parser was not changed
  after the eval run.
