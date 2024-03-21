from typing import Dict
from typing import List

from gopos.cadences.cadence import Cadence
from gopos.cadences.new_build import NewBuild

from gopos.timelines.cron import Cron


class Nightly(Cadence):
    """
    Subclass of Cadence which specifies a time every day

    Attributes
    ----------
    raw_hour : int
        Hour out of 24 (0-23)
    hour : str
        Hour in xx:xx format
    """
    def __init__(self, hour: str):
        self.raw_hour = int(hour)
        self.hour = Cadence.parse_hour(hour)

    @staticmethod
    def from_meta(meta: Dict) -> Cadence:
        hour = meta.get('hour')
        if not hour:
            raise KeyError(
                "{} must have an hour if nightly".format(meta['suite']))
        return Nightly(hour)

    def type(self) -> str:
        return "Nightly"

    def run_meta(self) -> str:
        return "at {}".format(self.hour)

    def __gt__(self, other):
        if type(other) == NewBuild:
            return True
        elif type(other) != Nightly:
            return False
        return self.raw_hour > other.raw_hour

    def __lt__(self, other):
        return not self.__gt__(other)

    def __eq__(self, other):
        return type(self) == type(other) and self.hour == other.hour

    def __hash__(self):
        return hash(self.__str__())

    def to_cron(self) -> List[Cron]:
        result = []
        for day in range(Cron.days_in_a_month()):
            result.append(Cron(day=day, hour=self.raw_hour))
        return result
