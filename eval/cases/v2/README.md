# eval/cases/v2 - analysis behind eval set v2

- `analyze_data.py` -> `data_analysis.json`: per destination market (catalog = data/inventory.json, what the tools use):
  listings allowing short stays (median min_nights <= 5), distance to center, price spread; flight density.
- `rank_routes.py` -> `route_ranking.json`: every origin -> destination route + date window (2-4 nights, T=2) ranked by
  the number of distinct feasible packages (out x back x lodging), exact dates and with +-1 day flex.
- `build_log_v2.json`: build statistics of `../build_eval_cases_v2.py` (candidates tested / passed / failed, reasons,
  and the re-test of the v1 conflicting cases).
