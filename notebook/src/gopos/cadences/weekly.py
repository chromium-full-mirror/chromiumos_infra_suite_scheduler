from typing import Dict
from typing import List

from gopos.cadences.cadence import Cadence

from gopos.timelines.cron import Cron


class Weekly(Cadence):
    """
    Subclass of Cadence which specifies a time every week

    Attributes
    ----------
    raw_day : int
        Day out of 7 (0-6) days
    raw_hour : int
        Hour out of 24 (0-23)
    day : str
        Day of the week (Monday-Sunday)
    hour : str
        Hour in xx:xx format
    """
    def __init__(self, day, hour):
        self.raw_day = int(day)
        self.raw_hour = int(hour)
        self.day = Cadence.DAY_LIST[int(day)]
        self.hour = Cadence.parse_hour(hour)

    @staticmethod
    def from_meta(meta: Dict) -> Cadence:
        day = meta.get('day')
        hour = meta.get('hour')
        if not day or not hour:
            raise KeyError(
                "{} must have a day and hour if weekly".format(meta['suite']))
        return Weekly(day, hour)

    def type(self) -> str:
        return "Weekly"

    def run_meta(self) -> str:
        return "on {} at {}".format(self.day, self.hour)

    def __gt__(self, other):
        if type(other) == NewBuild or type(other) == Nightly:
            return True
        elif self.raw_day == other.raw_day:
            return self.raw_hour > other.raw_hour
        else:
            return self.raw_day > other.raw_day

    def __lt__(self, other):
        if type(other) == NewBuild or type(other) == Nightly:
            return False
        elif self.raw_day == other.raw_day:
            return self.raw_hour < other.raw_hour
        else:
            return self.raw_day < other.raw_day

    def __eq__(self, other):
        return type(self) == type(
            other) and self.day == other.day and self.hour == other.hour

    def __hash__(self):
        return hash(self.__str__())

    def to_cron(self) -> List[Cron]:
        result = []
        # weeks in a cron month
        for week in range(Cron.weeks_in_month()):
            result.append(
                Cron(day=self.raw_day + (week * Cron.days_in_a_week()),
                     hour=self.raw_hour))
        return result
