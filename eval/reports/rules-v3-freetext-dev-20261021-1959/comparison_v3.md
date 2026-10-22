# Eval v3 - free-text segment (dev, 2026-10-21 19:59)

valid_plan (gold) = OK_PLAN and all final_checks pass against the hidden gold request. Key requirements: met / flagged (not met, but named as not handled) / ignored (not met, not mentioned).

| system | cases | valid_plan_rate (gold) [Wilson 95%] | direct | indirect | key req met / flagged / ignored (all) | direct | indirect | key_requirement_score all / direct / indirect | parse accuracy (core fields) | LLM calls / tokens per case |
|---|---|---|---|---|---|---|---|---|---|---|
| A - rules (keyword parser + strong rules) | 4 | 4/4 = 1.00 [0.51, 1.00] | 2/2 = 1.00 [0.34, 1.00] | 2/2 = 1.00 [0.34, 1.00] | 8 / 1 / 0 (of 9) | 4 / 0 / 0 (of 4) | 4 / 1 / 0 (of 5) | 0.92 / 1.00 / 0.83 | 1.00 | 0.0 / 0 |

By checker (met / flagged / ignored):

- A - rules (keyword parser + strong rules): budget_max 1/0/0; central_stay 1/0/0; day_window 1/0/0; evening_meal_within_km_of_lodging 0/1/0; no_activity_in_window 1/0/0; no_category 1/0/0; no_flight_departure_before 1/0/0; party_size 2/0/0; statuses {'OK_PLAN': 4}
