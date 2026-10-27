# מפרט סוכן המקומות

עודכן ב־27.10.2026. תפקיד פעיל ב־C בשם places. אחראי: שמואל. בודק נוסף: דניאל. ההיקף המחייב מפורט ב[דף הצוות](../TEAM_SCOPE_HE.md).

## אחריות והצדקה

בוחר אטרקציות ומסעדות לפי ההעדפות ומיקום הלינה כדי לרכז את התאמת התוכן ואת מקורות המידע. אינו מחליף חבילה ואינו משבץ פעילויות לימים ולשעות.

## הקלט המועבר כיום

city, interests, avoid, free_text, pace, מספר ימים ב־days, rain_days ו־lodging עם ref ו־lat/lon כאשר זמינים. מתווספים RULES_TEXT ומשוב מתיקון קודם אם קיים. מיקום הלינה מגיע אחרי בחירת החבילה. אין תלות ב־PlanningBrief או בסוכן GM.

## הכלים המורשים

- search_places(city, tags, indoor_only=False, near_lat=None, near_lon=None, limit=15, exclude_tags=[])
- get_place_details(place_id)

אלה פרמטרי מעטפת CrewAI ב־crew_tools.py. limit מוגבל לכל היותר ל־30. הקוד הפנימי ממפה near_lat/near_lon לזוג קואורדינטות. אין כתיבה לקובצי המקור ואין כלי תזמון.

## הפלט הקיים

הקטע הבא מועתק מ־models.py. פרטי המקור המלאים נשארים ביומן הכלים; אין להחליף את השדות במבנה חדש של evidence או fit_reason.

```python
class PlaceChoice(BaseModel):
    place_id: str
    category: str = ""
    indoor: str = "unknown"
    est_duration_min: int = 60
    matched_prefs: list[str] = Field(default_factory=list)
    reason: str = ""
    source_call_id: str = ""

class PlaceShortlist(BaseModel):
    places: list[PlaceChoice]
    uncovered_prefs: list[str] = Field(default_factory=list)
```

## בדיקות וניתוב

ההנחיה היא לבחור 8 עד 12 מקומות המכסים interests ומכבדים avoid. בימי גשם יש לכלול חלופות פנים. כל place_id ו־source_call_id צריכים להפנות למקור כלי קיים. כשל coverage יכול להחזיר את הסוכן פעם אחת; כל חזרה כפופה למגבלת הסבבים והזמן הכוללת.

## מגבלות ומצב אימות

max_iter=4 ועד 60 שניות להפעלה, בכפוף לזמן שנותר. דירוגים וביקורות סינתטיים אינם נחשפים לסוכנים. אין להמציא שעות פתיחה או לייחס ודאות למידע חסר. אטרקציות ומסעדות נכללות באותו סוכן קיים. אין להציג הנחיית prompt כאילו הוכחה בבדיקת הרצה חיה.
