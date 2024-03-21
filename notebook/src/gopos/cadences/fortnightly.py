import math
from gopos.cadences.cadence import Cadence
from gopos.cadences.new_build import NewBuild
from gopos.cadences.nightly import Nightly

from gopos.timelines.cron import Cron


class Fortnightly(Cadence):
    def __init__(self, day, hour):
        self.raw_day = int(day) % 7
        self.raw_hour = int(hour)
        self.day = Cadence.DAY_LIST[self.raw_day]
        self.hour = Cadence.parse_hour(hour)
        self.week = math.ceil(int(day) / 7)

    @staticmethod
    def from_meta(meta):
        day = meta.get('day')
        hour = meta.get('hour')
        if not day or not hour:
            raise KeyError(
                "{} must have a day and hour if fortnightly".format(
                    meta['suite']))
        return Fortnightly(day, hour)

    def type(self):
        return "Fortnightly"

    def run_meta(self):
        return "on week {}/2 on {} at {}".format(self.week, self.day, self.hour)

    def __gt__(self, other):
        if type(other) == NewBuild or type(other) == Nightly:
            return True
        return self.raw_day > other.raw_day and self.raw_hour > other.raw_hour

    def __lt__(self, other):
        return not self.__gt__(other)

    def __eq__(self, other):
        return type(self) == type(
            other) and self.day == other.day and self.hour == other.hour

    def __hash__(self):
        return hash(self.__str__())

    def to_cron(self) -> [Cron]:
        result = []
        for week in range(0, Cron.weeks_in_month(), 2):
            result.append(
                Cron(day=self.raw_day + (week * Cron.days_in_a_week()),
                     hour=self.raw_hour))
        return result
