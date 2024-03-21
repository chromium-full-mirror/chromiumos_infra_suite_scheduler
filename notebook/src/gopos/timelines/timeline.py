from typing import Dict
from typing import List

from gopos.timelines.cron import Cron

from gopos.suites.suite import Suite

from helpers import colors

from sortedcontainers import SortedDict


class Timeline:
    def __init__(self):
        self.timeline = {}

    def add_suite(self, suite: Suite):
        for cron in suite.cadence.to_cron():
            self.add_events(cron, [suite.name])

    def add_events(self, cron: Cron, events: List[str]):
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
        result = Timeline()
        for cron, events in self.timeline.items():
            result.add_events(cron.day % mod, events)
        return result

