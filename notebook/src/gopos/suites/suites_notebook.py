import re
from typing import List
from typing import Type

from gopos.cadences.cadence import Cadence
from gopos.suites.suite import Suite

from gopos.timelines.timeline import Timeline



class SuitesNotebook:
    def __init__(self, suites: List[Suite]):
        self.current = 0
        self.suites = suites

    def append(self, suite: Suite):
        self.suites.append(suite)

    def __len__(self):
        return len(self.suites)

    def __iter__(self):
        return self

    def __getitem__(self, item):
        if item > len(self):
            raise IndexError(f"{item} > {len(self)}")
        return self.suites[item]

    def __next__(self):
        if self.current >= len(self):
            raise StopIteration
        result = self.suites[self.current]
        self.current += 1
        return result

    def get_match_meta(self,
                       meta_name: str,
                       pools: List[str]) -> 'SuitesNotebook':
        results = []
        for suite in self.suites:
            if suite.meta.get(meta_name) in pools:
                results.append(suite)
        return SuitesNotebook(results)

    def get(self, name_regex: str) -> 'SuitesNotebook':
        results = []
        for suite in self.suites:
            if re.match(name_regex, suite.name):
                results.append(suite)
        return SuitesNotebook(results)

    def get_match_cadences(self, cadences: List[Type]):
        results = []
        for suite in self.suites:
            for cadence in cadences:
                if isinstance(suite.cadence, cadence):
                    results.append(suite)
        return SuitesNotebook(results)

    def get_match_time(self, time: Cadence):
        results = []
        for suite in self.suites:
            if suite.cadence.loose_equality(time):
                results.append(suite)
        return SuitesNotebook(results)

    def get_timeline(self, exclude_newbuild=False) -> Timeline:
        from gopos.cadences.new_build import NewBuild
        result = Timeline()
        for suite in self.suites:
            if exclude_newbuild and isinstance(suite.cadence, NewBuild):
                continue
            result.add_suite(suite)
        return result

    def __str__(self):
        return str(self.suites)

    def __repr__(self):
        return str(self)
