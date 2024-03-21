import re
from typing import List
from typing import Type

from gopos.cadences.cadence import Cadence
from gopos.suites.suite import Suite

from gopos.timelines.timeline import Timeline


class SuitesNotebook:
    """
    Container iterable which allows easy notebook-like introspection into
    a set of suites

    Attributes
    ----------
    suites: List[Suite]
        contained list of suites
    """
    def __init__(self, suites: List[Suite]):
        self._current = 0
        self.suites = suites

    def append(self, suite: Suite):
        """ Similar to list, allows one to append a Suite to this iterable """
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
        if self._current >= len(self):
            raise StopIteration
        result = self.suites[self._current]
        self._current += 1
        return result

    def get_match_meta(self,
                       meta_name: str,
                       vals: List[str]) -> 'SuitesNotebook':
        """
        Returns a SuitesNotebook object with all Suites which match the key-val
        pairing provided by meta-name (key) and pools (list of vals)

        Args:
            meta_name (str): The name of the key to match in suite
            vals (List[str]): values to match

        Returns:
            SuitesNotebook: notebook of all Suites which match
        """
        results = []
        for suite in self.suites:
            if suite.meta.get(meta_name) in vals:
                results.append(suite)
        return SuitesNotebook(results)

    def get(self, name_regex: str) -> 'SuitesNotebook':
        """
        Regex match of suite name

        Args:
            name_regex (str): Regex of name to match

        Returns:
            SuitesNotebook: notebook of all suites which match
        """
        results = []
        for suite in self.suites:
            if re.match(name_regex, suite.name):
                results.append(suite)
        return SuitesNotebook(results)

    def get_match_cadences(self, cadences: List[Type]) -> 'SuitesNotebook':
        """
        Cadence type match for suites

        Args:
            cadences (List[Type]): a list of all Cadence types to match

        Returns:
            SuitesNotebook: notebook of all suites which match
        """
        results = []
        for suite in self.suites:
            for cadence in cadences:
                if isinstance(suite.cadence, cadence):
                    results.append(suite)
        return SuitesNotebook(results)

    def get_match_time(self, time: Cadence) -> 'SuitesNotebook':
        """
        Cadence Object match for suites

        Args:
            time (Cadence): a specific time to match

        Returns:
            SuitesNotebook: notebook of all suites which match
        """
        results = []
        for suite in self.suites:
            if suite.cadence.loose_equality(time):
                results.append(suite)
        return SuitesNotebook(results)

    def get_timeline(self, exclude_newbuild: bool = False) -> Timeline:
        """
        Constructs a timeline object for this given notebook

        Args:
            exclude_newbuild (bool): Whether to include newbuilds in the
            notebook. Added, since newbuild times aren't technically accurate.

        Returns:
            Timeline: a Timeline object representative of this notebook
        """
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
