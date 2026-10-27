# מפרט מנהל הטיול

עודכן ב־27.10.2026. תפקיד פעיל ב־C בשם trip_manager. אחראית: גלית. בודק נוסף: רן. ההיקף המחייב מפורט ב[דף הצוות](../TEAM_SCOPE_HE.md).

## אחריות והצדקה

בוחר טיסות הלוך וחזור, לינה ורכב לפי הצורך ומנמק פשרות, משום שהחלטות החבילה מחייבות איזון משותף בין מחיר, תאריכים ומיקום. אינו בוחר מקומות, אינו מתזמן ואינו מנתב את הסוכנים האחרים.

## הקלט המועבר כיום

המשימה מקבלת request מתוך TripRequest, nights, top5_candidates מתומחרים עם price_call_id ו־city_airports. מתווספים RULES_TEXT ומשוב בדיקות אם יש תיקון. אין brief של GM. קוד build_candidates מכין את המועמדים לפני הפעלת הסוכן.

## הכלים המורשים

ממשק CrewAI נקבע ב־crew_tools.py. הפרמטרים הבאים מועברים בשמותיהם:

- search_flights(origin, airports, date, min_seats, direction)
- search_hotels(city, check_in, check_out, guests, central=False)
- search_cars(airport, start, end, travelers)
- calculate_price(flight_out, flight_back, stay, travelers, nights, car=None)

אין חיפוש מקומות, כלי מסלול או כתיבה לקטלוג. המחיר חייב להישען על תוצאת calculate_price מההרצה.

## הפלט הקיים

הקטע הבא מועתק מ־models.py. אין שדה status או selected_package_refs בתוך PackageDecision. המרת ההחלטה ל־Package ולסטטוס הריצה מתבצעת בקוד.

```python
class PackageDecision(BaseModel):
    flight_out_ref: str
    flight_back_ref: str
    hotel_ref: str
    car_ref: Optional[str] = None
    price_call_id: str
    total_price: float
    tradeoffs: list[str] = Field(default_factory=list)
    relaxed_constraint: Optional[str] = None
    rationale: str = Field(default="", max_length=600)
```

## בדיקות וניתוב

תקציב, תאריכים, קיבולת ורכב נבדקים בקוד. כשל בחבילה או HOTEL_TOO_FAR חוזר למנהל הטיול בתוך המגבלות הכוללות. בחירה חדשה מאפסת את המקומות ואת המסלול. מזהים, מחיר ו־price_call_id חייבים להיות מגובים ביומן הכלים.

## מגבלות ומצב אימות

max_iter=4 ו־max_execution_time עד 60 שניות להפעלה, בכפוף לזמן שנותר למערכת. עד שלושה סבבים ו־270 שניות למערכת כולה. קיבולת רכב היא אומדן; מעל ארבעה נוסעים עם רכב מטופלים כחוסר מידע בקוד המשותף. מחיר החבילה אינו כולל בהכרח את כל העמלות או עלויות הפעילויות. קיום הסוכן בקוד אינו הוכחת הצלחה מול Gemini.
