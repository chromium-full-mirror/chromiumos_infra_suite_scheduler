from typing import Dict
from typing import List

from gopos.timelines.cron import Cron

from gopos.suites.suite import Suite

from helpers import colors

from sortedcontainers import SortedDict


class Timeline:
    """
    Representation of a charted timeline with the ability to manipulate
    for Data Science. Extracted from a set of Suites in a Suite notebook.

    Attributes
    ----------
    timeline: Dict
        Internal representation of timeline which can be user-visible
    """
    def __init__(self):
        self.timeline = {}

    def add_suite(self, suite: Suite):
        """ Adds a suite to the timeline """
        for cron in suite.cadence.to_cron():
            self.add_events(cron, [suite.name])

    def add_events(self, cron: Cron, events: List[str]):
        """
        Adds a generic event to the timeline.

        Args:
            cron (Cron): Temporal definition of event (i.e.: wen it runs)
            events (List): A string definition for event which runs at cron
        """
        self.timeline.setdefault(cron, [])
        self.timeline[cron] += events

    def __str__(self):
        result = ""
        for cron in sorted(self.timeline):
            num_items = len(self.timeline[cron])
            preamble = str(cron) + ' [x' + str(num_items) + ']'
            result += f"{preamble:<30}: " \
                      f"{colors.white('|'*num_items if num_items < 80 else '|' * 40 + ' ... ' + '|' * 40)}\n"
        return result

    def __repr__(self):
        return str(self)

    def get_top(self, x: int) -> Dict[int, Cron]:
        """
        Return a sorted Dict containing the times with the largest amount
        of events.

        Args:
            x (int): Number of events to filter by. E.g.: 3 returns top 3
            highest numbers; note that there may be more crons, but numbers
            will be 3 (if there are equal events).

        Returns:
            Dict: A sorted dictionary of event, sorted by largest events in that
            cron

        """
        result = SortedDict()
        for cron in self.timeline:
            if len(result) < x:
                result[len(self.timeline[cron])] = [cron]
            elif len(self.timeline[cron]) > min(result):
                if result.get(len(self.timeline[cron])):
                    result[len(self.timeline[cron])].append(cron)
                else:
                    result.pop(min(result))
                    result[len(self.timeline[cron])] = [cron]
        return result

    def per(self, mod: int = Cron.days_in_a_month()) -> 'Timeline':
        """
        Returns a timeline with a different cadence than the built-in 28.
        Value should be smaller than 28, but not strictly enforced. Greater than
        28 just returns 28. Allows users to define by weekly or fortnight, or
        as desired.

        Args:
            mod (int): How many days to have the cadence of the timeline be

        Returns:
            Timeline: A new timeline with the desired cadence.
        """
        result = Timeline()
        for cron, events in self.timeline.items():
            result.add_events(cron.day % mod, events)
        return result

