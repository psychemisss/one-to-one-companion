import pendulum

from app.config import settings


def now():
    return pendulum.now(settings.app.timezone)


def today():
    return now().date()


def parse(s):
    return pendulum.parse(s)


def to_date(s):
    return parse(s).date()


def days_since(s):
    return (today() - to_date(s)).days


def next_due(last_date, cadence_days):
    return to_date(last_date).add(days=cadence_days)


def humanize(s, lang):
    d = to_date(s)
    if d == today():
        return None  # caller shows the translated "today"
    return d.diff_for_humans(locale=lang)


def fmt_date(s, lang):
    return to_date(s).format("D MMM YYYY", locale=lang) if s else ""
