import datetime


# Return next exact half hour, i.e. HH:30:00 or HH:00:00
def next_update_time(t):
    r = t.replace(second=0, microsecond=0)
    r += datetime.timedelta(minutes=(30 - (t.minute % 30)))
    return r
