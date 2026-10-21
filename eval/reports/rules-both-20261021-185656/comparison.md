# Comparison (2026-10-21 18:56)

valid_plan = OK_PLAN and all final_checks pass and time <= 300 s and rounds <= 3. D = eval cases A-D with a feasible oracle, restricted to the cases in each run.

| system | cases | valid_plan_rate (D) [Wilson 95%] | conflicting B-D [Wilson 95%] | correct_refusal (E) | time mean / p95 (s) | LLM calls mean / max | tokens / case | rounds mean | grounding / schema fails | coverage mean | rain_handled | E correct status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A - rules | 40 (all, eval) | 36/36 = 1.00 [0.90, 1.00] | 24/24 = 1.00 [0.86, 1.00] | 4/4 | 0.01 / 0.01 | 0.0 / 0 | 0 | 1.00 | 0 / 0 (of 36 plans) | 0.99 | 8/8 | 4/4 |

Failure histogram (runs with a plan, by check) and status counts:

- A - rules: failures {}; statuses {'OK_PLAN': 36, 'NO_PACKAGE_IN_CATALOG': 3, 'NEEDS_DATA': 1}; plan quality on D: 2.17 activities / full day, 5 empty full days, 28 travel min / day
