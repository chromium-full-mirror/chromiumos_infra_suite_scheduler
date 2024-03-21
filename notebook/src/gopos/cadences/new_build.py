from typing import Dict
from typing import List

from gopos.cadences.cadence import Cadence

from gopos.timelines.cron import Cron


class NewBuild(Cadence):
    """
    Subclass of Cadence which specifies to run every new build (usually ~00:00)
    """
    def __init__(self):
        pass

    @staticmethod
    def from_meta(meta: Dict) -> Cadence:
        return NewBuild()

    def type(self) -> str:
        return "New Build"

    def run_meta(self) -> str:
        return ""

    def __gt__(self, other):
        return False

    def __lt__(self, other):
        return not self.__gt__(other)

    def __eq__(self, other):
        return type(self) == type(other)

    def __hash__(self):
        return hash("new build")

    def to_cron(self) -> List[Cron]:
        result = []
        for day in range(Cron.days_in_a_month()):
            result.append(Cron(day=day, hour=0))
        return result
