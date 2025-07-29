import datetime
from django.template import Library

register = Library()

@register.filter
def repeat(string, times):
    return (
        "" if times is None or times == 0 or times == "" else
        string * times
    )


@register.filter
def matchdate(m, show_date=True):
    d = (
        m.datetime_last_period if m.period_count > 0 else
        m.datetime_started if m.datetime_started is not None else
        m.datetime
    )

    if d is None:
        return ""

    # Convert to local time
    dl = d.astimezone()
    n = datetime.datetime.now().astimezone()

    # Convert to string with special case for today
    date = dl.strftime("%Y-%m-%d")
    date_now = n.strftime("%Y-%m-%d")
    return (
        dl.strftime("%H:%M") if date == date_now else
        dl.strftime(f"{date} %H:%M")
    )
