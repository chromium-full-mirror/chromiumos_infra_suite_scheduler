from abc import ABC, abstractmethod

from gopos.timelines.cron import Cron


# TODO fix comparisons


class Cadence(ABC):

    DAY_LIST = ['Monday',
                'Tuesday',
                'Wednesday',
                'Thursday',
                'Friday',
                'Saturday',
                'Sunday']

    def __init__(self):
        pass

    @staticmethod
    def parse(meta):
        from gopos.cadences.fortnightly import Fortnightly
        from gopos.cadences.new_build import NewBuild
        from gopos.cadences.nightly import Nightly
        from gopos.cadences.weekly import Weekly
        cadence = meta.get("run_on")
        if not cadence:
            raise KeyError("No run_on field for {}".format(meta['suite']))
        if cadence == "weekly":
            return Weekly.from_meta(meta)
        elif cadence == "new_build":
            return NewBuild.from_meta(meta)
        elif cadence == "nightly":
            return Nightly.from_meta(meta)
        elif cadence == "fortnightly":
            return Fortnightly.from_meta(meta)
        else:
            raise KeyError("Unknown cadence: {}".format(cadence))

    @abstractmethod
    def type(self):
        pass

    @abstractmethod
    def run_meta(self):
        pass

    @staticmethod
    @abstractmethod
    def from_meta(meta):
        pass

    @staticmethod
    def parse_hour(hour):
        return "{}:00 {}".format(int(hour) % 12,
                                 ("am" if (int(hour) < 12) else "pm"))

    def __str__(self):
        return "{} {}".format(self.type(), self.run_meta())

    def __repr__(self):
        return self.__str__()

    def loose_equality(self, other):
        if type(other) == type(self) == NewBuild:
            return True
        elif type(other) == NewBuild or type(self) == NewBuild:
            return False
        elif type(other) == Nightly or type(self) == Nightly:
            return self.hour == other.hour
        else:
            return self.hour == other.hour and self.day == other.day

    @abstractmethod
    def to_cron(self) -> [Cron]:
        pass
