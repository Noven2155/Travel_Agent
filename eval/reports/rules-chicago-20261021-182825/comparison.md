# Comparison (2026-10-21 18:28)

valid_plan = OK_PLAN and all final_checks pass and time <= 300 s and rounds <= 3. D = eval cases A-D with a feasible oracle, restricted to the cases in each run.

| system | cases | valid_plan_rate (D) [Wilson 95%] | conflicting B-D [Wilson 95%] | correct_refusal (E) | time mean / p95 (s) | LLM calls mean / max | tokens / case | rounds mean | grounding / schema fails | coverage mean | rain_handled | E correct status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A - rules | 24 (chicago, eval) | 22/22 = 1.00 [0.85, 1.00] | 15/15 = 1.00 [0.80, 1.00] | 2/2 | 0.01 / 0.01 | 0.0 / 0 | 0 | 1.00 | 0 / 0 (of 22 plans) | 0.99 | 6/6 | 2/2 |

Failure histogram (runs with a plan, by check) and status counts:

- A - rules: failures {}; statuses {'OK_PLAN': 22, 'NO_PACKAGE_IN_CATALOG': 2}; plan quality on D: 2.24 activities / full day, 3 empty full days, 29 travel min / day
