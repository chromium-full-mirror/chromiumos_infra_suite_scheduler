import logging
import sys
import argparse
import code
from argparse import Namespace
from typing import Dict

from gopos.suites.suite import Suite
from helpers import colors
import os
from tqdm import tqdm

from helpers.git import Git
from gopos.suites.suites_notebook import SuitesNotebook

# included for users to interact
from gopos.cadences.fortnightly import Fortnightly
from gopos.cadences.new_build import NewBuild
from gopos.cadences.nightly import Nightly
from gopos.cadences.weekly import Weekly

# For autocomplete
import readline
import rlcompleter
if 'libedit' in readline.__doc__:
    readline.parse_and_bind("bind ^I rl_complete")
else:
    readline.parse_and_bind("tab: complete")

log = logging.getLogger()


_CHANGED_KEY = 'changed'
_REMOVED_KEY = 'removed'

SUITES = SuitesNotebook([])
CHANGES = {_CHANGED_KEY: set(), _REMOVED_KEY: set()}


def interact():
    """ Starts the REPL """
    try:
        import readline
    except ImportError:
        readline = None

    code.InteractiveConsole(
        locals=globals()).interact(
        banner="",
        exitmsg="Thank you for playing Wing Commander!")


def prompt():
    """ Adds explanatory prompt to users """
    print("\n\nWelcome to the interactive Susch explorer!")
    print("Suites are stores in a {} class, and Cadences in {} class.".format(
        colors.red("Suite"), colors.red("Cadence")))
    print(
        "{} contains a list of all populated suites. Good luck, You'll need "
        "it!\n\n".format(
            colors.red("SUITES")))


def changes_prompt(suite_map: Dict):
    """ Adds information about suite changes if calculated """
    print(f"For the iterations provided, "
          f"{colors.red(str(len(CHANGES[_CHANGED_KEY])))} changed, "
          f"and {colors.red(str(len(CHANGES[_REMOVED_KEY])))} removed.\n")
    if CHANGES[_CHANGED_KEY]:
        print(colors.white("Changed are:"))
        for change in sorted(CHANGES[_CHANGED_KEY]):
            print(f"{colors.blue(change)}")
    if CHANGES[_REMOVED_KEY]:
        print(colors.white("Removed are:"))
        for change in sorted(CHANGES[_REMOVED_KEY]):
            print(f"{colors.red(change)} at {colors.red(suite_map[change].version_name)}")


def parse_args() -> Namespace:
    """ Arg parser setup """
    parser = argparse.ArgumentParser(
        prog='SuSchParser',
        description='Parses and allows you to interact with Suite Scheduler '
                    'Configs',
        epilog='Contact jaquesc@ with questions')
    parser.add_argument('-s', '--source', action='store',
                        default="../generated_configs/suite_scheduler.ini",
                        dest='source',
                        help="Path to Suite Scheduler file to parse ("
                             "suite_scheduler.ini)")
    parser.add_argument('-r', '--reload', action='store_true',
                        help="Whether to reload the source file with git")
    parser.add_argument('-b', '--build-history', dest='history_amount',
                        default=0,
                        help="Set to a positive number to look back x git"
                             "changed when building the suites. Note this"
                             "will be a slow process depending on how large x"
                             "is, as several git calls are required")
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help="Defines how verbose output will be.")
    return parser.parse_args()


def build_suites(source_file: str) -> Dict:
    """
    Builds the SUITES Suite object and returns a dict of suites mapped by name
    Args:
        source_file (str): Suites file to tokenize

    Returns:
        suite_map (Dict): suite of dicts mapped by name
    """
    suite_map = {}

    with open(source_file, 'r') as susch_ini:
        while True:
            next_suite = Suite.parse(susch_ini)
            if not next_suite:
                break
            suite_map[next_suite.name] = next_suite
            SUITES.append(next_suite)
    return suite_map


def build_previous(source_file: str, source_hash: str, suite_map: Dict):
    """
    Builds previous suites for SUITES based on git responses and amount of
    traceback specified by user

    Args:
        source_file (str): Previous version file to build history from
        source_hash (str): The git hash representing this version
        suite_map (Dict): Dict to use to know what was built
    """
    with open(source_file, 'r') as susch_ini:
        while True:
            next_suite = Suite.parse(susch_ini)
            if not next_suite:
                break
            if next_suite.name in suite_map:
                next_suite.version_name = source_hash
                # Diff found between versions
                if ((next_suite - suite_map[next_suite.name])
                    or (suite_map[next_suite.name] - next_suite)):
                    CHANGES[_CHANGED_KEY].add(next_suite.name)
                    suite_map[next_suite.name].previous_version = next_suite
                    suite_map[next_suite.name] = next_suite
            else:
                CHANGES[_REMOVED_KEY].add(next_suite.name)
                suite_map[next_suite.name] = next_suite


def _setup_logging(log_level: int):
    """
    Simple logger setup

    Args:
        log_level (int): Desired log level
    """
    if log_level <= 0:
        log_level = 10
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    handler.setLevel(log_level)
    log.addHandler(handler)


def main():
    args = parse_args()
    source_file = args.source
    reload_source = args.reload
    history_amount = int(args.history_amount)

    _setup_logging(30 - (int(args.verbosity) * 10))

    if not os.path.isfile(source_file):
        sys.stderr.write(f"Source file {source_file} cannot be found.\n")
        sys.exit(1)

    git = Git(source_file)

    if reload_source:
        git.pull()

    suite_map = build_suites(source_file)
    if history_amount:
        for version in tqdm(range(1, history_amount + 1)):
            build_previous(*git.get_previous(version), suite_map)

    if history_amount:
        changes_prompt(suite_map)
    prompt()
    interact()


if __name__ == "__main__":
    main()
