import re
import pprint
from typing import Dict
from typing import Set

from gopos.cadences.cadence import Cadence
from helpers import colors

NAME_PATTERN = re.compile("\[(.*)\]\n")
_KEYS_KEY = "keys"
_VALUES_KEY = "values"
_ADDED_KEY = "added"
_REMOVED_KEY = "removed"
_CHANGED_KEY = "changed"


class Suite:
    def __init__(self, name):
        self.name = name
        self.meta = {}
        self.previous_version = None
        self.version_name = None

    @staticmethod
    def _parse_name(line: str):
        pattern = NAME_PATTERN.match(line)
        if not pattern:
            raise KeyError("Name is not in correct format: {}".format(line))
        return Suite(pattern.group(1))

    def _parse_kv(self, line: str) -> None:
        key, value = line.split(':', 1)
        value = value.strip()
        self.meta[key] = value

    def equal(self, key: str, value: str) -> bool:
        return self.meta.get(key, False) == value

    def has_no(self, key: str):
        return not self.meta.get(key)

    def has_prev(self) -> bool:
        return self.previous_version is not None

    def _finalize(self):
        self.cadence = Cadence.parse(self.meta)

    def __str__(self):
        return f"\n\n{colors.white('Name')}: {self.name}\n{colors.white('Cadence')}: {self.cadence}\n{colors.white('Meta')}: {pprint.pformat(self.meta)}"

    def __repr__(self):
        return self.__str__()

    # TODO make better
    def diff_prev(self) -> Dict[str, Set]:
        if not self.previous_version:
            return None
        fields_added = list(set(self.meta) - set(self.previous_version.meta))
        fields_removed = list(set(self.previous_version.meta) - set(self.meta))
        fields_changed = {}

        for key, value in self.meta.items():
            if key in fields_added:
                continue

            if ',' not in value:
                if self.previous_version.meta[key] != self.meta[key]:
                   fields_changed[key] = \
                       f"Value changed from " \
                       f"{self.previous_version.meta[key]} to" \
                       f"{self.meta[key]}"
            else:
                # Assuming list
                current_value_list = value.split(", ")
                prev_value_list = self.previous_version.meta[key].split(", ")
                fields_changed[key] = {
                    _ADDED_KEY: list(set(current_value_list) - set(prev_value_list)),
                    _REMOVED_KEY: list(set(prev_value_list) - set(current_value_list))
                }


        return {
            _ADDED_KEY: fields_added,
            _REMOVED_KEY: fields_removed,
            _CHANGED_KEY: fields_changed
        }

    # TODO make better and pretty print
    def __sub__(self, other) -> Set:
        return set(self.meta.items()) - set(other.meta.items())

    @staticmethod
    def parse(file_iterator):
        line = file_iterator.readline()
        if line == '':
            return None
        suite = Suite._parse_name(line)

        while True:
            line = file_iterator.readline()
            if line == "\n" or line == '':
                # end tokenization
                break
            suite._parse_kv(line)

        suite._finalize()
        return suite