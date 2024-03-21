from abc import ABC, abstractmethod
from typing import Dict
from typing import List

from gopos.timelines.cron import Cron


class Cadence(ABC):
    """ An abstract class to represent a Scheduling Cadence """

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
    def parse(meta: Dict) -> 'Cadence':
        """
        Factory method to create a cadence from suite dict input
        Args:
            meta (Dict): Dictionary of items to extract cadence from

        Returns:
            Cadence: A cadence corresponding to input
        """
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
    def type(self) -> str:
        """ String exemplification of type """
        pass

    @abstractmethod
    def run_meta(self) -> str:
        """ String exemplification of the cadence """
        pass

    @staticmethod
    @abstractmethod
    def from_meta(meta: Dict) -> 'Cadence':
        """
        Defines the cadence for the object based on suite dict

        Args:
            meta (Dict): Dictionary of items to extract cadence from

        Returns:
            Cadence: A cadence corresponding to input
        """
        pass

    @staticmethod
    def parse_hour(hour: str) -> str:
        """
        Returns hour string definition (xx:00 [am|pm]) from int hour

        Args:
            hour (str): The hour to convert
        Returns:
            str: xx:00 [am|pm]
        """
        return "{}:00 {}".format(int(hour) % 12,
                                 ("am" if (int(hour) < 12) else "pm"))

    def __str__(self):
        return "{} {}".format(self.type(), self.run_meta())

    def __repr__(self):
        return self.__str__()

    def loose_equality(self, other: 'Cadence') -> bool:
        """
        Whether two different Cadence items should be considered loosely the
        same (e.g.: if a weekly and a nightly run on the same hour they
        technically overlap)

        Args:
            other (Cadence): Other Cadence to compare to

        Returns:
            bool: True if they are loosely equal, False otherwise
        """
        if type(other) == type(self) == NewBuild:
            return True
        elif type(other) == NewBuild or type(self) == NewBuild:
            return False
        elif type(other) == Nightly or type(self) == Nightly:
            return self.hour == other.hour
        else:
            return self.hour == other.hour and self.day == other.day

    @abstractmethod
    def to_cron(self) -> List[Cron]:
        """
        Get Cron definition of this Cadence for timeline. As some cases can have
        more than one Cron (e.g.: Nightly should have 28 crons in a timeline)
        we return a list

        Returns:
            List[Cron]: All Crons in the timeline which match this Cadence
        """
        pass
