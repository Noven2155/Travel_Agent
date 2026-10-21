# Eval v3 - free-text segment (eval, 2026-10-21 19:59)

valid_plan (gold) = OK_PLAN and all final_checks pass against the hidden gold request. Key requirements: met / flagged (not met, but named as not handled) / ignored (not met, not mentioned).

| system | cases | valid_plan_rate (gold) [Wilson 95%] | direct | indirect | key req met / flagged / ignored (all) | direct | indirect | key_requirement_score all / direct / indirect | parse accuracy (core fields) | LLM calls / tokens per case |
|---|---|---|---|---|---|---|---|---|---|---|
| A - rules (keyword parser + strong rules) | 20 | 9/20 = 0.45 [0.26, 0.66] | 7/10 = 0.70 [0.40, 0.89] | 2/10 = 0.20 [0.06, 0.51] | 48 / 0 / 8 (of 56) | 28 / 0 / 0 (of 28) | 20 / 0 / 8 (of 28) | 0.85 / 1.00 / 0.70 | 0.99 | 0.0 / 0 |

By checker (met / flagged / ignored):

- A - rules (keyword parser + strong rules): budget_max 17/0/0; car_included 2/0/0; day_window 3/0/0; evening_meal_within_km_of_lodging 0/0/2; flag_unsupported 4/0/0; max_walk_leg 2/0/0; min_count_category 8/0/1; near_cheapest 1/0/0; no_activity_in_window 3/0/1; no_category 1/0/1; no_flight_departure_before 2/0/1; nonstop_flights 1/0/0; party_size 3/0/1; priority_respected 1/0/1; statuses {'OK_PLAN': 20}
