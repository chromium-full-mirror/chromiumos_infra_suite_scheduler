# SuiteNotebook

SuiteNotebook is a REPL which allows one to introspect Suites and their cadences based on the suite_scheduler.ini source of truth

## Installation

As the package is python, no installation is necessary, but one must make sure they have suite_scheduler.ini present inside of a git repo, so that it may be read an instrospected. As SuitesNotebook is present in the same repo as suite_scheduler.ini, it is expected that the file be present when this code is pulled.

## Usage


To instantiate the notebook, run any of the following:

```bash
# Run directly
python3 src/parser.py

# Define a suite_scheduler.ini source file outside thde default location
python3 src/parser.py -s location_to/suite_scheduler.ini

# Auto-reload to latest ini version
python3 src/parser.py -r

# Build 1000 previous versions of each config (useful for navigating changes to config)
python3 src/parser.py -b 1000

```

At this point a REPL is instantiated (the REPL should have auto-complete enabled, so all usages should be discoverable via TAB, and `help()` allows one to introspect methods and classes. Following are examples of usage:

```python
# Show all SUITES
> SUITES

# Get a specific suite by name (note this allows regex)
> SUITES.get('some_suite')

# Get all suites in a specific pool
> SUITES.get_match_meta('pool', ['wificell'])

# Get all suites at a specific cadence (options are Fortnightly, Weekly, Nightly, NewBuild)
> SUITES.get_match_cadences([Weekly])

# Get Suites that match one specific time
> SUITES.get_match_time(Weekly(day=0, hour=0))

# Find the difference between a Suite and its previous iteration (assuming it has one)
> SUITES.get('WeeklyPowerDaily')[0].diff_prev()

# Find the commit hash of previous version
> SUITES.get('WeeklyPowerDaily')[0].previous_version.version_name

# Print a Timeline (note you can filter the suites by some attribute and call timeline on that as well)
> SUITES.get_timeline()

# Get top 5 fullest days in timeline
> SUITES.get_timeline().get_top(5)

# Change cadence of timeline (below example shows weekly vs 28 days)
> SUITES.get_timeline().per(7)
```

Note as this is a REPL, you can easily manipulate any of the above, if you want more detail. E.g.:

```python
for suite in SUITES:
   if int(suite.timeout) > 39:
     print(suite)
```
