# Comparison (2026-10-21 19:14)

valid_plan = OK_PLAN and all final_checks pass and time <= 300 s and rounds <= 3. D = eval cases A-D with a feasible oracle, restricted to the cases in each run.

| system | cases | valid_plan_rate (D) [Wilson 95%] | conflicting B-D [Wilson 95%] | correct_refusal (E) | time mean / p95 (s) | LLM calls mean / max | tokens / case | rounds mean | grounding / schema fails | coverage mean | rain_handled | E correct status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A - rules | 40 (all, eval) | 35/36 = 0.97 [0.86, 1.00] | 23/24 = 0.96 [0.80, 0.99] | 4/4 | 0.02 / 0.05 | 0.0 / 0 | 0 | 1.00 | 0 / 0 (of 36 plans) | 0.97 | 6/6 | 4/4 |

v2 secondary metrics (true-conflict cases = groups B-D of eval_cases_v2; valid_plan unchanged):

| system | soft_pref_satisfaction (mean) | conflict_handling (mean) | detected | acceptable sacrifice | explained | full handling [Wilson 95%] | quality pass (D plans) | quality failures by check | interest relevance (mean share) |
|---|---|---|---|---|---|---|---|---|---|
| A - rules | 0.29 (n=24) | 0.18 (n=24) | 0/24 | 13/24 | 0/24 | 0/24 = 0.00 [0.00, 0.14] | 3/35 | no_empty_full_day 3, opening_plausibility 17, interest_relevance 7, no_back_to_back_duplicate 25 | 0.87 |


Failure histogram (runs with a plan, by check) and status counts:

- A - rules: failures {'coverage': 1}; statuses {'OK_PLAN': 35, 'CONFLICT_UNRESOLVED': 1, 'NO_PACKAGE_IN_CATALOG': 3, 'NEEDS_DATA': 1}; plan quality on D: 2.45 activities / full day, 3 empty full days, 32 travel min / day
