# מפרט מפתח: מומחה אטרקציות ומסעדות

סטטוס: תפקיד קיים כ־places; המפרט כולל גם חיפוש מסעדות. מיועד למפתח/ת עצמאי/ת.

## אחריות וגבולות
להחזיר shortlist מותאם לתחומי עניין ולהעדפות, עם מקורות ונימוק. אין להציג דירוגים, ביקורות או price_level סינתטיים; אין להמציא שעות פתיחה/מחיר. העדפות כמו "מקומי" הן שיקול איכותני ולא עובדה בדאטא.

## קלט
request:TripRequest; planning_brief:PlanningBrief; city:string= request.city; place_catalog:list[PlaceSummary] או תוצאות search_places; prior_feedback:list[string]?.
TripRequest: TripRequest (models.py): request_id:string; city:Chicago|New York; origin:string(3, uppercase); start_date/end_date:date; travelers:int 1–6; budget_usd:int>0; wants_car:boolean; pace:relaxed|normal|packed (normal); interests:list[Interest] 1–4 from food,culture,attractions,nightlife,family,nature,shows,shopping,extreme/adventure; avoid:list[Interest]=[]; hotel_preference:any|central (any); as_of:date; free_text?:string; depart_flex_days/return_flex_days:int 0–1; soft_prefs:list[central,nonstop,exact_dates,dry_days,long_days,under_preferred_budget]; preferred_budget_usd?:int; request_text?:string (original); daily_blocked_windows:list[{start:HH:MM,end:HH:MM,label:string}]; max_walk_minutes?:int; day_start/day_end?:HH:MM; accessibility:boolean=false (unsupported data); no_early_flight_before?:HH:MM; priority_weights:map[string,float]; unparsed_requirements:list[string].
PlaceSummary: place_id,name,category,tags,indoor(true|false|unknown),lat,lon,neighborhood,in_wikivoyage,has_wikidata,typical_visit_minutes,typical_visit_minutes_basis,source,license. פרטי שעות/אתר/כתובת/תיאור מגיעים מ־get_place_details.

## כלים מורשים
search_places(city,tags,indoor_only=false,near?:[lat,lon],limit=30,exclude_tags=[])
get_place_details(place_id,city?)
כלי המקום מחזיר מעטפת call_id/source/license/data_date יחד עם places[]/n/status אפשרי. לא נכתבים נתונים חזרה ל־CSV.

## פלט קיים
PlaceShortlist: places:list[PlaceChoice]; uncovered_prefs:list[string]=[].
PlaceChoice: place_id:string; category:string=""; indoor:string="unknown"; est_duration_min:int=60; matched_prefs:list[string]=[]; reason:string=""; source_call_id:string="".
source_call_id חייב להפנות לתוצאת כלי ביומן. הקוד הציבורי הנוכחי אינו מחזיר subcategory אף שהיא רשומה כשדה ציבורי בקובץ.

## זרימה וקבלה
לבנות שאילתות tags מתוך interests/avoid ו־brief; לאזן אטרקציות ומסעדות לפי הצורך; להביא details לשעות פתיחה; unknown נשאר unknown; לדווח uncovered_prefs.
בדוק שכל place_id ומקור קיימים, שאין שדות synthetic אסורים, ושכל פלט תואם schema. קובץ עיר חסר: NEEDS_DATA; מקום לא נמצא: להשמיט ולדווח; שגיאה בכלי: שגיאה מפורשת ותוצר חלקי אם קיים.