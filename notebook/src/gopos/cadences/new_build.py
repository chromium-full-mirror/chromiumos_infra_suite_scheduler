from gopos.cadences.cadence import Cadence

from gopos.timelines.cron import Cron


class NewBuild(Cadence):
    def __init__(self):
        pass

    @staticmethod
    def from_meta(meta):
        return NewBuild()

    def type(self):
        return "New Build"

    def run_meta(self):
        return ""

    def __gt__(self, other):
        return False

    def __lt__(self, other):
        return not self.__gt__(other)

    def __eq__(self, other):
        return type(self) == type(other)

    def __hash__(self):
        return hash("new build")

    def to_cron(self) -> [Cron]:
        result = []
        for day in range(Cron.days_in_a_month()):
            result.append(Cron(day=day, hour=0))
        return result
