# רעיון שמור מחוץ להיקף: סוכן מנהל כללי (GM)

**החלטת היקף 27.10.2026:** מסמך רעיון בלבד, מחוץ להיקף המאושר לקראת 30.10. אין לפתח רכיב זה במסגרת המשימות הנוכחיות. [דף הצוות](../TEAM_SCOPE_HE.md) גובר על הוראות הפיתוח בהמשך המסמך. התוכן הישן נשמר לעקיבות ואינו מתאר יכולת קיימת.
סטטוס: מבנה יעד חדש ל־C; אינו ממומש בקוד. מיועד למפתח/ת סוכן.

## מטרה וסמכות
סוכן LLM שמפרש את הבקשה החופשית, נותן הקשר למומחים, משלב תוצרים ומכריע בפשרות. אין לו כלי חיפוש. הוא רשאי לבחור רק מבין אפשרויות עם מזהי מקור/קריאות כלי. קוד validators הוא הסמכות הבלעדית לאילוצים קשיחים.

## קלט
שלב brief: request:TripRequest; original_request_text:string; candidate_context:{packages:Package[],places:PlaceSummary[]}; data_status:string[]; stage=brief.
שלב decision: אותם request/text; planning_brief:PlanningBrief; package_decision:PackageDecision; place_shortlist:PlaceShortlist; itinerary:ItineraryPlan; validator_report:CheckReport; reviewer_report:QualitativeReview; stage=decision.
שדות TripRequest המלאים: TripRequest (models.py): request_id:string; city:Chicago|New York; origin:string(3, uppercase); start_date/end_date:date; travelers:int 1–6; budget_usd:int>0; wants_car:boolean; pace:relaxed|normal|packed (normal); interests:list[Interest] 1–4 from food,culture,attractions,nightlife,family,nature,shows,shopping,extreme/adventure; avoid:list[Interest]=[]; hotel_preference:any|central (any); as_of:date; free_text?:string; depart_flex_days/return_flex_days:int 0–1; soft_prefs:list[central,nonstop,exact_dates,dry_days,long_days,under_preferred_budget]; preferred_budget_usd?:int; request_text?:string (original); daily_blocked_windows:list[{start:HH:MM,end:HH:MM,label:string}]; max_walk_minutes?:int; day_start/day_end?:HH:MM; accessibility:boolean=false (unsupported data); no_early_flight_before?:HH:MM; priority_weights:map[string,float]; unparsed_requirements:list[string].

## פלט מוצע חדש
PlanningBrief: priorities:[{statement:string,source_text:string,confidence:low|medium|high}]; tensions:[{items:string[],options:string[]}]; assumptions:string[]; clarification_needed:boolean; question:string|null; routing:string[].
DecisionRecord: selected_package_refs:{flight_out_ref:string,flight_back_ref:string,hotel_ref:string,car_ref:string|null}; selected_place_ids:string[]; accepted_tradeoffs:string[]; unresolved:string[]; rationale:string; evidence_call_ids:string[].
יש להגדיר שני מודלי Pydantic פנימיים. אין להוסיף אותם ל־API בלי החלטת גרסה.

## זרימה
1. לשמר את הטקסט המקורי ולהבחין בין hard constraints, העדפות, והנחות.
2. להחזיר brief למומחי חבילות ומקומות.
3. בשלב הסיום לעיין בדוח validators ובביקורת, להכריע ולנתב לכל היותר תיקון ממוקד אחד.
4. אם עמימות משנה מהותית את ההמלצה, להחזיר clarification_needed; אין להמציא תשובה.

## כלים/כתיבה/כשלים
אין כלי חיפוש. קריאה רק מהקשר הריצה. כתיבה ל־PlanningBrief/DecisionRecord פנימיים ו־events בלבד, לעולם לא לקובצי מקור.
503/כשל מודל: סטטוס טכני ושימור תוצרים חלקיים. JSON לא תקין: ניסיון schema-repair מוגבל אחד ואז כשל.
קבלה: אין עובדה ללא evidence_call_id; לא משנה מחיר/זמינות; לא עוקף hard validator; לפחות event עם agent_id, stage, זמנים, usage/error; עד סבב תיקון אחד.
