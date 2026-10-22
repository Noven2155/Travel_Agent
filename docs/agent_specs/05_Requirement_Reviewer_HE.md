# מפרט מפתח: מבקר דרישות איכותני

סטטוס: תפקיד חדש בתכנון C; אינו קיים בקוד. המימוש עצמאי, קריטריוני ההערכה משותפים ל־QA.

## מטרה וגבולות
להעריך התאמה סמנטית של התוכנית לבקשה המקורית ולהעדפות רכות, עם ראיות. לא מאשר budget/date/capacity, לא משנה all_checks_passed, ולא עוקף validators. אין חיפוש חיצוני.

## קלט
original_request_text:string; request:TripRequest; final_package:Package; itinerary:ItineraryPlan; place_details:list[PlaceSummary]; tool_evidence:list[{call_id,tool,source,data_date,output_summary}]; validator_report:CheckReport.
TripRequest: TripRequest (models.py): request_id:string; city:Chicago|New York; origin:string(3, uppercase); start_date/end_date:date; travelers:int 1–6; budget_usd:int>0; wants_car:boolean; pace:relaxed|normal|packed (normal); interests:list[Interest] 1–4 from food,culture,attractions,nightlife,family,nature,shows,shopping,extreme/adventure; avoid:list[Interest]=[]; hotel_preference:any|central (any); as_of:date; free_text?:string; depart_flex_days/return_flex_days:int 0–1; soft_prefs:list[central,nonstop,exact_dates,dry_days,long_days,under_preferred_budget]; preferred_budget_usd?:int; request_text?:string (original); daily_blocked_windows:list[{start:HH:MM,end:HH:MM,label:string}]; max_walk_minutes?:int; day_start/day_end?:HH:MM; accessibility:boolean=false (unsupported data); no_early_flight_before?:HH:MM; priority_weights:map[string,float]; unparsed_requirements:list[string].
Package: refs,price_lines,total,price_call_id,flight_out?,flight_back?,stay?,car?,fees_complete. CheckReport: checks:list[{name,passed,details[]}], coverage?, rain_days[].

## פלט מוצע חדש: QualitativeReview
assessments:list[{preference_text:string,status:fit|tension|unknown,evidence_call_ids:string[],evidence_fields:string[],rationale:string}]; missing_evidence:string[]; suggested_revision:string|null; overall_summary:string.
להגדיר Pydantic model נפרד לפני מימוש. אין לשנות את API result בלי החלטת API version.

## תהליך
1. לזהות העדפות רכות רק מהטקסט המקורי, כגון "רגוע", "מקומי", "לא עמוס"; לא להמיר לדרישות קשיחות.
2. להשוות לתוכנית ולמקורות שהתקבלו. לכל fit/tension לצרף evidence_call_ids; אם חסר מידע, unknown.
3. להעביר ל־GM תיקון ממוקד אחד לכל היותר; המבקר אינו משנה את התוכנית בעצמו.
4. hard validator fail מוצג בנפרד; קוד הוא הסמכות.

## כלים, תקלות וקבלה
ללא tools וכתיבה לנתוני המקור. פלט שגוי → INVALID_OUTPUT; כשל מודל/503 → UNAVAILABLE; לעולם לא success.
בדיקות: אין העדפה שאינה בטקסט; אין fit/tension בלי ראיות; לא יכול לאשר/לדרוס בדיקת קוד; נימוק תמציתי; JSON תקין. למדוד מול rubric אנושי סמוי, המבקר אינו ground truth.