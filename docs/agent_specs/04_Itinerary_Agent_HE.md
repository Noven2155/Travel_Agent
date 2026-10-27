# מפרט סוכן המסלול

עודכן ב־27.10.2026. תפקיד פעיל ב־C בשם itinerary. אחראי: דניאל. בודקת נוספת: גלית. ההיקף המחייב מפורט ב[דף הצוות](../TEAM_SCOPE_HE.md).

## אחריות והצדקה

משבץ מקומות לימים ולשעות לפי נסיעות, קצב ומזג אוויר כדי לרכז את בדיקת האפשרות לבצע את התוכנית. אינו מחפש מקומות חדשים ואינו מחליף חבילה.

## הקלט המועבר כיום

pace, travel_mode, lodging_ref, day_windows, weather, places ו־interests. רשומות places מועשרות מהיומן ב־place_id, name, category, tags, indoor, minutes ו־opening_hours. מתווספים RULES_TEXT ומשוב אם קיים. אין reviewer בסוף הזרימה. לא כל TripRequest מועבר כיום במפורש למשימה; אכיפת שדות נוספים דורשת בדיקה נפרדת.

## הכלים המורשים

- get_travel_time(pairs, mode='transit') כאשר pairs הוא רשימת זוגות מזהים
- check_day_load(day_items, pace, edge_day=False)

הכלים מחושבים בקוד. זמני הנסיעה הם אומדן גיאוגרפי, ואין להציגם כניווט חי. check_day_load מחשב מגבלות; final_checks בודק את התוכנית לאחר החזרת הסוכן.

## הפלט הקיים

הקטע הבא מועתק מ־models.py. המסלול נשמר ב־days[].items; אין מבנה activities חדש. start ו־end הם מחרוזות HH:MM בשעה המקומית.

```python
class Item(BaseModel):
    place_id: str
    name: str = ""
    kind: Literal["activity", "meal"] = "activity"
    start: str            # HH:MM local city time
    end: str
    mode: Literal["walk", "transit", "drive"]
    travel_min: int
    travel_call_id: str
    from_id: str = ""     # previous location (stay ref or place_id); used by the travel check
    weather_note: Optional[str] = None

class DayPlan(BaseModel):
    date: str
    items: list[Item] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    window: Optional[tuple[str, str]] = None

class Dropped(BaseModel):
    place_id: str
    reason: str

class ItineraryPlan(BaseModel):
    status: Literal["OK", "CANNOT_SCHEDULE"] = "OK"
    days: list[DayPlan] = Field(default_factory=list)
    dropped: list[Dropped] = Field(default_factory=list)
    cannot_reason: Optional[Literal["DAY_LOAD", "TRAVEL_TIME", "WEATHER", "HOTEL_TOO_FAR"]] = None
    explanation: str = ""
```

## בדיקות וניתוב

כשל day_load, travel או weather_rule חוזר למסלול. HOTEL_TOO_FAR מחזיר למנהל הטיול. כשל כיסוי עשוי להחזיר קודם ל־places פעם אחת. תוצאה שאינה עוברת בדיקות אינה מאושרת רק משום שהסוכן מסביר אותה. מקום שלא שובץ נרשם ב־dropped עם סיבה.

## מגבלות ומצב אימות

max_iter=5 ועד 75 שניות להפעלה, בכפוף לזמן שנותר. config.py קובע relaxed עד שתי פעילויות, שש שעות ושישים דקות נסיעה; normal שלוש פעילויות, שמונה שעות ותשעים דקות; packed חמש פעילויות, עשר שעות ומאה ועשרים דקות. הארוחות אינן נספרות כפעילויות אך נכללות בשעות. ביום הגעה או עזיבה לכל היותר פעילות אחת; עד שתי ארוחות ביום. תחילת יום הגעה לאחר נחיתה ועוד 90 דקות וסיום יום עזיבה לפני המראה פחות 180 דקות. קיום השדות וההנחיות אינו הוכחת הרצה מול מודל אמיתי.
