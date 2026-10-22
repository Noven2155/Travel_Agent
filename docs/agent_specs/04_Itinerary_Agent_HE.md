# מפרט מפתח: מומחה מסלול

סטטוס: תפקיד קיים כיום כ־itinerary. מיועד למפתח/ת עצמאי/ת.

## אחריות וגבולות
לתזמן shortlist לימים, לפי חבילה, שעות, חלונות חסומים, קצב, מרחק ומזג אוויר. לא משנה חבילה, לא ממציא שעות, ולא טוען לזמני ניווט חיים. זמני נסיעה הם אומדן קוד גיאוגרפי.

## קלט
request:TripRequest; package:PackageDecision; package_details:Package; places:PlaceShortlist; place_details:list[object]; day_conditions:list[DayCondition]; previous_feedback:list[string]?.
TripRequest: TripRequest (models.py): request_id:string; city:Chicago|New York; origin:string(3, uppercase); start_date/end_date:date; travelers:int 1–6; budget_usd:int>0; wants_car:boolean; pace:relaxed|normal|packed (normal); interests:list[Interest] 1–4 from food,culture,attractions,nightlife,family,nature,shows,shopping,extreme/adventure; avoid:list[Interest]=[]; hotel_preference:any|central (any); as_of:date; free_text?:string; depart_flex_days/return_flex_days:int 0–1; soft_prefs:list[central,nonstop,exact_dates,dry_days,long_days,under_preferred_budget]; preferred_budget_usd?:int; request_text?:string (original); daily_blocked_windows:list[{start:HH:MM,end:HH:MM,label:string}]; max_walk_minutes?:int; day_start/day_end?:HH:MM; accessibility:boolean=false (unsupported data); no_early_flight_before?:HH:MM; priority_weights:map[string,float]; unparsed_requirements:list[string].
DayCondition: date,lead_days,precip_mm?,precip_h?,apparent_max?,gust_max?,flags[],source,fetched_at.
PackageDecision: flight_out_ref,flight_back_ref,hotel_ref,car_ref?,price_call_id,total_price,tradeoffs[],relaxed_constraint?,rationale.
כלי מקום עשוי לכלול opening_hours,website,address,description_short,source_url.

## כלים מורשים
get_travel_time(pairs:[[from_id,to_id]],mode=walk|transit|drive)
check_day_load(day_items,pace,edge_day=false)
אין חיפוש מקום/לינה/טיסות.

## פלט קיים: ItineraryPlan
status:OK|CANNOT_SCHEDULE; days:DayPlan[]; dropped:Dropped[]; cannot_reason:DAY_LOAD|TRAVEL_TIME|WEATHER|HOTEL_TOO_FAR|null; explanation:string.
DayPlan: date:string; items:Item[]; flags:string[]; window?:[HH:MM,HH:MM].
Item: place_id,name,kind=activity|meal,start,end,mode=walk|transit|drive,travel_min:int,travel_call_id,from_id,weather_note?.
Dropped: place_id,reason (WEATHER/NO_SLOT/DAY_LOAD/CLOSED).
הקונפיגורציה קובעת relaxed עד 2 פעילויות/6 שעות/60 דקות נסיעה; normal 3/8/90; packed 5/10/120; עד 2 ארוחות ביום; יום הגעה/עזיבה פעילות אחת; buffers 90/180 דקות.

## בדיקות וקבלה
אין פעילות בחלון חסום; שעות היום והטיסות מכובדות; כל מקום קיים וכל נסיעה קשורה ל־call_id; day load עובר check_day_load. שעות פתיחה לא ידועות מסומנות. אי אפשר לתזמן: CANNOT_SCHEDULE עם סיבה; אין להסתיר מקומות שנפלו.