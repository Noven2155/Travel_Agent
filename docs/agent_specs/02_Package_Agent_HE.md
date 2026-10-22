# מפרט מפתח: מומחה חבילות

סטטוס: התפקיד קיים ב־C הנוכחי בשם trip_manager. מטרת מסמך זה לתת למפתח/ת ממשק ממוקד.

## אחריות וגבולות
בחירת טיסת הלוך/חזור, לינה ורכב אם נדרש; להציג מחיר ופשרות. אין הזמנה ואין זמינות חיה. קיבולת רכב היא אומדן; מעל 4 נוסעים מוחזר NEEDS_DATA. העלות אינה כוללת בהכרח את כל העמלות.

## קלט
request:TripRequest; planning_brief:PlanningBrief; candidates:list[Package] או תוצאות כלים; previous_feedback:list[string]?; weather:list[DayCondition].
TripRequest: TripRequest (models.py): request_id:string; city:Chicago|New York; origin:string(3, uppercase); start_date/end_date:date; travelers:int 1–6; budget_usd:int>0; wants_car:boolean; pace:relaxed|normal|packed (normal); interests:list[Interest] 1–4 from food,culture,attractions,nightlife,family,nature,shows,shopping,extreme/adventure; avoid:list[Interest]=[]; hotel_preference:any|central (any); as_of:date; free_text?:string; depart_flex_days/return_flex_days:int 0–1; soft_prefs:list[central,nonstop,exact_dates,dry_days,long_days,under_preferred_budget]; preferred_budget_usd?:int; request_text?:string (original); daily_blocked_windows:list[{start:HH:MM,end:HH:MM,label:string}]; max_walk_minutes?:int; day_start/day_end?:HH:MM; accessibility:boolean=false (unsupported data); no_early_flight_before?:HH:MM; priority_weights:map[string,float]; unparsed_requirements:list[string].
Package קיים: refs:{flight_out:string,flight_back:string,stay:string,car:string|null}; price_lines:{flights:number,lodging:number,car:number}; total:number; price_call_id:string; flight_out/flight_back/stay/car:object|null; fees_complete:boolean.

## כלים מורשים
search_flights(origin,airports,date,min_seats,direction=out|back)
search_hotels(city,check_in,check_out,guests,central=false)
search_cars(airport,start,end,travelers)
calculate_price(refs:{flight_out,flight_back,stay,car},travelers,nights)
אין כלי מקומות/מסלול או כתיבה לקטלוג.

## פלט קיים: PackageDecision
flight_out_ref:string; flight_back_ref:string; hotel_ref:string; car_ref:string|null; price_call_id:string; total_price:number; tradeoffs:list[string]=[]; relaxed_constraint:string|null; rationale:string עד 600 תווים. כל ref ו־price_call_id חייבים להופיע ביומן הכלים.
calculate_price מחזיר refs, travelers, nights, lines{flights,lodging,car}, total, rental_days?, fees_complete=false, currency=USD. זה מקור הסכום התקף.

## זרימת עבודה וקבלה
חפש טיסות בכל חלונות הגמישות, עם min_seats=travelers; חפש לינה לפי עיר/תאריכים/אורחים; רכב רק אם נדרש; חשב total בכלי; השווה לתקציב הקשיח ואז דרג העדפות רכות.
אין הצעה: NO_PACKAGE_IN_CATALOG. מידע חסר: NEEDS_DATA. ref לא תקין: INVALID_REF. ספק נכשל: TECHNICAL_ERROR.
בדיקות: סכום תואם לכלי; אין עובדה/מחיר מומצאים; תאריכים/קיבולת/נוסעים תקינים; פלט Pydantic תקף.