# Comparison (2026-10-21 19:24)

valid_plan = OK_PLAN and all final_checks pass and time <= 300 s and rounds <= 3. D = eval cases A-D with a feasible oracle, restricted to the cases in each run.

| system | cases | valid_plan_rate (D) [Wilson 95%] | conflicting B-D [Wilson 95%] | correct_refusal (E) | time mean / p95 (s) | LLM calls mean / max | tokens / case | rounds mean | grounding / schema fails | coverage mean | rain_handled | E correct status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A0 - rules basic | 8 (all, dev) | 7/7 = 1.00 [0.65, 1.00] | 5/5 = 1.00 [0.57, 1.00] | 1/1 | 0.03 / 0.16 | 0.0 / 0 | 0 | 1.00 | 0 / 0 (of 7 plans) | 1.00 | 1/1 | 1/1 |
| A - rules strong | 8 (all, dev) | 7/7 = 1.00 [0.65, 1.00] | 5/5 = 1.00 [0.57, 1.00] | 1/1 | 0.05 / 0.19 | 0.0 / 0 | 0 | 1.00 | 0 / 0 (of 7 plans) | 1.00 | 1/1 | 1/1 |

v2 secondary metrics (true-conflict cases = groups B-D of eval_cases_v2; valid_plan unchanged):

| system | soft_pref_satisfaction (mean) | conflict_handling (mean) | detected | acceptable sacrifice | explained | full handling [Wilson 95%] | quality pass (D plans) | quality failures by check | interest relevance (mean share) |
|---|---|---|---|---|---|---|---|---|---|
| A0 - rules basic | 0.40 (n=5) | 0.27 (n=5) | 0/5 | 4/5 | 0/5 | 0/5 = 0.00 [0.00, 0.43] | 0/7 | no_empty_full_day 0, opening_plausibility 6, interest_relevance 3, no_back_to_back_duplicate 3 | 0.64 |
| A - rules strong | 0.50 (n=5) | 1.00 (n=5) | 5/5 | 5/5 | 5/5 | 5/5 = 1.00 [0.57, 1.00] | 7/7 | no_empty_full_day 0, opening_plausibility 0, interest_relevance 0, no_back_to_back_duplicate 0 | 1.00 |


Failure histogram (runs with a plan, by check) and status counts:

- A0 - rules basic: failures {}; statuses {'OK_PLAN': 7, 'NEEDS_DATA': 1}; plan quality on D: 2.36 activities / full day, 0 empty full days, 34 travel min / day
- A - rules strong: failures {}; statuses {'OK_PLAN': 7, 'NEEDS_DATA': 1}; plan quality on D: 2.71 activities / full day, 0 empty full days, 39 travel min / day
