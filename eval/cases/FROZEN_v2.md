# Frozen eval set v2 (true-conflict cases)

`eval_cases_v2.json` (40 eval + 8 dev cases, Chicago + New York) is the current case set; `eval_cases.json` (v1,
`FROZEN.sha256`) is kept unchanged for history. `python -m eval.run_eval` uses v2 by default (`--cases v1` for the old set).

    sha256(eval_cases_v2.json) = see FROZEN_v2.sha256   (verify: cd eval/cases && sha256sum -c FROZEN_v2.sha256)

What changed vs v1
- Groups A (easy) and E (infeasible) and dev V01/V05/V06 are copied from v1 unchanged, except that New York
  `oracle_places` is now filled from `data/places/nyc_places.csv` (all PASS).
- The 24 conflicting cases (B01-B12, C01-C06, D01-D06) and dev V02/V03/V04/V07/V08 were rebuilt by
  `build_eval_cases_v2.py` (seed 20261030). In v1 they were conflicts only by description: re-testing them with the
  true-conflict test gives 0/29 passes (B01 had exactly one feasible package).
- New optional request fields (defaults = v1 behaviour): `depart_flex_days`, `return_flex_days` (0-1; trip length may
  change by at most one night), `soft_prefs` (central, nonstop, exact_dates, dry_days, long_days,
  under_preferred_budget), `preferred_budget_usd`. New York is multi-airport (JFK/LGA/EWR) as before.
- Every B-D case stores `conflict_type`, `competing_prefs`, `true_conflict` (n_feasible_packages, profiles,
  acceptable_sacrifices = Pareto front, pareto_options with the cheapest package of each option).

True-conflict test (build_eval_cases_v2.py): enumerate every package that passes the hard constraints incl. budget
(out x back x lodging [x car], every allowed date pair). TRUE CONFLICT iff (i) no feasible package satisfies all soft
preferences and (ii) >= 2 Pareto-optimal packages sacrifice different preferences; plus >= 20 feasible packages.
Route/date windows are tried densest first (#distinct packages). `tests/test_eval_v2.py` checks that the shared
pipeline (`build_candidates`) finds exactly the same number of feasible packages and the same Pareto front.

Scoring (eval/quality.py, secondary - valid_plan_rate stays central): soft_pref_satisfaction, conflict_handling
(detected / acceptable sacrifice / explained), quality checks (no_empty_full_day, opening_plausibility,
interest_relevance, no_back_to_back_duplicate). Thresholds were set on the dev split only (`python -m eval.score
<dir> --dev`): the only change from the initial values was allowing a MEAL at a bar/pub from 11:00 (dev V08).

Rules for v2 are those of v1: tune only on dev, all three systems on the same frozen file / fixtures / commit, any
change -> new version and a re-run of all systems.
