# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module of reader for suite tasks config file."""

import collections
import logging
import re

import build_event
import build_lib
import constants
import rest_client
import task
import timed_event
import tot_manager


# Handled event classes
EVENT_CLASSES = {
    'nightly': timed_event.Nightly,
    'weekly': timed_event.Weekly,
    'new_build': build_event.NewBuild,
}

# Namedtuple for storing event settings.
EventSettings = collections.namedtuple(
    'EventSettings',
    [
        'always_handle',
        'event_hour',
    ])

# Common task entries
COMMON_TASK_ENTRIES = [
    'any_model',
    'board_families',
    'boards',
    'branch_specs',
    'cros_build_spec',
    'day',
    'dimensions',
    'exclude_board_families',
    'exclude_boards',
    'exclude_models',
    'firmware_ro_build_spec',
    'firmware_rw_build_spec',
    'force',
    'frontdoor',
    'hour',
    'job_retry',
    'lc_branches',
    'lc_targets',
    'models',
    'no_delay',
    'num',
    'only_hwtest_sanity_required',
    'os_type',
    'pool',
    'priority',
    'qs_account',
    'suite',
    'test_source',
    'timeout',
]

# Namedtuple for storing task info.
TaskInfo = collections.namedtuple(
    'TaskInfo',
    COMMON_TASK_ENTRIES + ['name', 'keyword', 'testbed_dut_count']
    )
TaskInfo.__new__.__defaults__ = (None,) * len(TaskInfo._fields)

# The regex for testbed dut count
_TESTBED_DUT_COUNT_REGEX = r'[^,]*-(\d+)'


class MalformedConfigEntryError(Exception):
  """Raised to indicate a config parsing failure."""


class TaskConfig(object):
  """Class for reading task config file for suite scheduler."""

  _ALLOWED_HEADER = set(COMMON_TASK_ENTRIES + ['owner', 'run_on'])

  def __init__(self, config_reader, is_sanity=False):
    """Initialize a TaskConfig to generate task list from config file.

    Args:
      config_reader: a ConfigReader object to read task config.
      is_sanity: a boolean; true if we are running in sanity env.
    """
    self._config_reader = config_reader
    self.is_sanity = is_sanity
    self._tot_manager = tot_manager.TotMilestoneManager(is_sanity=is_sanity)
    self._board_family_config = {}
    if not is_sanity:
      self._board_family_config = build_lib.get_board_family_mapping_from_gs(
          rest_client.StorageRestClient(
              rest_client.BaseRestClient(
                  constants.RestClient.STORAGE_CLIENT.scopes,
                  constants.RestClient.STORAGE_CLIENT.service_name,
                  constants.RestClient.STORAGE_CLIENT.service_version)))

  def get_tasks_by_keyword(self, event_type):
    """Obtain tasks from config sections read from config file.

    Args:
      event_type: the event_type for the tasks to fetch,
        like 'new_build'.

    Returns:
      a dict containing successfully parsed 'tasks' and 'exceptions', which
      combines all parsing errors.
    """
    tasks = []
    exceptions = []
    for section in self._config_reader.sections():
      try:
        if event_type == self._get_keyword(section):
          new_task = self._create_task_from_config_section(section)
          tasks.append(new_task)
      except MalformedConfigEntryError as e:
        exceptions.append(str(e))
        logging.exception(str(e))
        continue

    return {'tasks': tasks, 'exceptions': exceptions}

  def get_event_setting(self, section_name):
    """Fetch event settings from config file by given section name.

    Args:
      section_name: the section to fetch event settings.

    Returns:
      an EventSettings object.
    """
    always_handle = self._config_reader.getboolean(
        section_name, 'always_handle')
    event_hour = self._config_reader.getint(section_name, 'hour')
    return EventSettings(always_handle=always_handle,
                         event_hour=event_hour)

  def _get_keyword(self, section):
    run_on = self._config_reader.getstring(section, 'run_on')
    if run_on is None:
      raise MalformedConfigEntryError(
          'run_on is not specified for %s' % section)

    return run_on

  def _get_testbed_dut_count(self, board_entry):
    """Parse boards from launch control targets.

    Args:
      board_entry: the entry for 'boards' in task config file. It could
        be a string of board list or a single board.

    Returns:
      None if no board_entry or board_entry represents a board list or
      board_entry doesn't contain testbed_dut_count. Otherwise return
      an int representing testbed dut.
    """
    testbed_dut_count = None
    if board_entry:
      match = re.match(_TESTBED_DUT_COUNT_REGEX, board_entry)
      if match:
        testbed_dut_count = int(match.group(1))

    return testbed_dut_count

  def _parse_boards_from_launch_control_targets(self, os_type, lc_targets):
    """Parse boards from launch control targets.

    Args:
      os_type: the task's os type.
      lc_targets: the launch control target.

    Returns:
      None if os_type is not in launch control os types, & no lc_targets.
      Otherwise, return a string of board list, where boards are split by
      comma.
    """
    boards = None
    if (os_type in build_lib.OS_TYPES_LAUNCH_CONTROL and
        lc_targets is not None):
      boards = ''
      for target in lc_targets.split(','):
        try:
          lc_target_info = build_lib.parse_launch_control_target(
              target.strip())
        except ValueError:
          continue

        boards += '%s,' % build_lib.get_board_by_android_target(
            lc_target_info.target)

      boards = boards.strip(',')

    return boards

  def _read_task_section(self, section):
    """Read the task secton in task config file.

    Args:
      section: a String section name to read.

    Returns:
      A TaskInfo object includes contents in the given section.

    Raises:
      MalformedConfigEntryError: if a config entry is invalid.
    """
    any_model = self._config_reader.getboolean(section, 'any_model')
    board_families = self._config_reader.getstring(section, 'board_families')
    boards = self._config_reader.getstring(section, 'boards')
    cros_build_spec = self._config_reader.getstring(section, 'cros_build_spec')
    exclude_board_families = self._config_reader.getstring(
            section, 'exclude_board_families')
    exclude_boards = self._config_reader.getstring(section, 'exclude_boards')
    exclude_models = self._config_reader.getstring(section, 'exclude_models')
    firmware_ro_build_spec = self._config_reader.getstring(
            section, 'firmware_ro_build_spec')
    firmware_rw_build_spec = self._config_reader.getstring(
            section, 'firmware_rw_build_spec')
    keyword = self._config_reader.getstring(section, 'run_on')
    lc_branches = self._config_reader.getstring(section, 'lc_branches')
    lc_targets = self._config_reader.getstring(section, 'lc_targets')
    models = self._config_reader.getstring(section, 'models')
    pool = self._config_reader.getstring(section, 'pool')
    qs_account = self._config_reader.getstring(section, 'qs_account')
    suite = self._config_reader.getstring(section, 'suite')
    test_source = self._config_reader.getstring(section, 'test_source')

    _b_s = self._config_reader.getstring(section, 'branch_specs')
    branch_specs = [] if _b_s is None else re.split(r'\s*,\s*', _b_s)
    os_type = self._config_reader.getstring(section, 'os_type')
    os_type = build_lib.OS_TYPE_CROS if os_type is None else os_type
    timeout = self._config_reader.getint(section, 'timeout')
    timeout = EVENT_CLASSES[keyword].TIMEOUT if timeout is None else timeout

    force = bool(self._config_reader.getboolean(section, 'force'))
    frontdoor = not bool(self._config_reader.getboolean(section, 'not_frontdoor'))
    job_retry = bool(self._config_reader.getboolean(section, 'job_retry'))
    no_delay = bool(self._config_reader.getboolean(section, 'no_delay'))

    priority = self._config_reader.getint(section, 'priority')
    # Default priority is not needed for suites pool and other pools with
    # qs_account attached, because they have enabled quota scheduler.
    if priority is None and pool != 'suites' and qs_account is None:
      priority = EVENT_CLASSES[keyword].PRIORITY

    only_hwtest_sanity_required = self._config_reader.getstring(
        section, 'only_hwtest_sanity_required')

    try:
      num = self._config_reader.getint(section, 'num')
    except ValueError as e:
      raise MalformedConfigEntryError('Ill-specified |num|: %s' % e)

    try:
      hour = self._config_reader.getint(section, 'hour')
    except ValueError as e:
      raise MalformedConfigEntryError('Ill-specified |hour|: %s' % e)

    try:
      day = self._config_reader.getint(section, 'day')
    except ValueError as e:
      raise MalformedConfigEntryError('Ill-specified |day|: %s' % e)

    testbed_dut_count = self._get_testbed_dut_count(boards)
    lc_boards = self._parse_boards_from_launch_control_targets(
        os_type, lc_targets)
    # In some cases 'boards' originally is like ***-2, and needs to be
    # reset to  real boards from lc_targets. It follows current
    # suite-scheduler's logic, which set testbed_dut_count as property
    # for each task.
    # It's possible that testbed_dut_count is attached to every lc_target,
    # not to every task. Filed crbug.com/755221 for tracking.
    if lc_boards is not None:
      boards = lc_boards

    families = set()
    if board_families:
      families.update(board_families.split(','))
    if exclude_board_families:
      families.update(exclude_board_families.split(','))
    if any(family not in self._board_family_config for family in families):
      raise MalformedConfigEntryError(
          'Invalid board family in list: %r\nBoard family name should be in '
          '%r' % (families, self._board_family_config.keys()))

    dimensions = self._config_reader.getstring(section, 'dimensions')

    return TaskInfo(
        any_model=any_model,
        board_families=board_families,
        boards=boards,
        branch_specs=branch_specs,
        cros_build_spec=cros_build_spec,
        day=day,
        dimensions=dimensions,
        exclude_board_families=exclude_board_families,
        exclude_boards=exclude_boards,
        exclude_models=exclude_models,
        firmware_ro_build_spec=firmware_ro_build_spec,
        firmware_rw_build_spec=firmware_rw_build_spec,
        force=force,
        frontdoor=frontdoor,
        hour=hour,
        job_retry=job_retry,
        keyword=keyword,
        lc_branches=lc_branches,
        lc_targets=lc_targets,
        models=models,
        name=section,
        no_delay=no_delay,
        num=num,
        only_hwtest_sanity_required=only_hwtest_sanity_required,
        os_type=os_type,
        pool=pool,
        priority=priority,
        qs_account=qs_account,
        suite=suite,
        test_source=test_source,
        testbed_dut_count=testbed_dut_count,
        timeout=timeout,
    )

  def _validate_task_section(self, task_info):
    """Validate a task section.

    Args:
      task_info: a TaskInfo object.

    Raises:
      MalformedConfigEntryError: if any item in section is not valid.
    """
    if not task_info.keyword:
      raise MalformedConfigEntryError('%s: No |run_on|.' % task_info.name)

    if not task_info.suite:
      raise MalformedConfigEntryError('%s: No |suite|.' % task_info.name)

    if task_info.hour is not None and (
        task_info.hour < 0 or task_info.hour > 23):
      raise MalformedConfigEntryError(
          '%s: |hour| must be an integer between 0 and 23.' %
          task_info.name)

    if (task_info.hour is not None and
        task_info.keyword not in ['nightly', 'weekly']):
      raise MalformedConfigEntryError(
          '%s: |hour| represents a timepoint of a day, that can '
          'only apply to nightly/weekly event.' % task_info.name)

    if task_info.day is not None and (
        task_info.day < 0 or task_info.day > 6):
      raise MalformedConfigEntryError(
          '%s: |day| must be an integer between 0 and 6, where 0 is '
          'for Monday and 6 is for Sunday.' % task_info.name)

    if task_info.day is not None and task_info.keyword != 'weekly':
      raise MalformedConfigEntryError(
          '%s: |day| represents a day of a week, that can '
          'only apply to weekly events.' % task_info.name)

    if task_info.branch_specs:
      try:
        tot_manager.check_branch_specs(
            task_info.branch_specs, self._tot_manager)
      except ValueError as e:
        raise MalformedConfigEntryError('%s: %s' % task_info.name,
                                        str(e))

    self._check_os_type(task_info)
    self._check_testbed_parameter(task_info)
    self._check_firmware_parameter(task_info)

  def _check_os_type(self, task_info):
    """Verify whether os_type is capatible."""
    if task_info.os_type not in build_lib.OS_TYPES:
      raise MalformedConfigEntryError(
          '|os_type| must be one of %r' % build_lib.OS_TYPES)

    if task_info.os_type == build_lib.OS_TYPE_CROS and (
        task_info.lc_branches or task_info.lc_targets):
      raise MalformedConfigEntryError(
          '|branches| and |targets| are only supported for Launch '
          'Control builds, not ChromeOS builds.')

    if (task_info.os_type in build_lib.OS_TYPES_LAUNCH_CONTROL and
        (not task_info.lc_branches or not task_info.lc_targets)):
      raise MalformedConfigEntryError(
          '|branches| and |targets| must be specified for Launch '
          'Control builds.')

  def _check_firmware_parameter(self, task_info):
    """Verify firmware-related parameters."""
    if ((task_info.firmware_rw_build_spec or
         task_info.firmware_ro_build_spec or
         task_info.cros_build_spec) and
        task_info.test_source not in [build_lib.BuildType.FIRMWARE_RW,
                                      build_lib.BuildType.FIRMWARE_RO,
                                      build_lib.BuildType.CROS]):
      raise MalformedConfigEntryError(
          'You must specify the build for test source. It can only '
          'be firmware_rw, firmware_ro or cros.')

    if task_info.firmware_rw_build_spec and task_info.cros_build_spec:
      raise MalformedConfigEntryError(
          'You cannot specify both firmware_rw_build_spec and '
          'cros_build_spec. firmware_rw_build_spec is used to '
          'specify a firmware build when the suite requires '
          'firmware to be updated in the dut, its value can only be '
          'firmware or cros. cros_build_spec is used to specify '
          'a ChromeOS build when build_specs is set to firmware.')

    if (task_info.firmware_rw_build_spec and
        task_info.firmware_rw_build_spec not in ['firmware', 'cros']):
      raise MalformedConfigEntryError(
          'firmware_rw_build_spec can only be empty, firmware or '
          'cros. It does not support other build type yet.')

  def _check_testbed_parameter(self, task_info):
    """Verify testbed-related parameters."""
    if (task_info.os_type not in build_lib.OS_TYPES_LAUNCH_CONTROL and
        task_info.testbed_dut_count):
      raise MalformedConfigEntryError(
          'testbed_dut_count is only applicable to testbed to run '
          'test with launch control builds.')

  def _create_task_from_config_section(self, section):
    """Create a Task from a section of a config file.

    The section to parse should look like this:
    [TaskName]
    suite: suite_to_run  # Required
    run_on: event_on which to run  # Required
    hour: integer of the hour to run, only applies to nightly. # Optional
    branch_specs: factory,firmware,>=R12 or ==R12 # Optional
    pool: pool_of_devices  # Optional
    num: sharding_factor  # int, Optional
    boards: board1, board2  # comma separated string, Optional
    frontdoor: is_frontdoor # bool, Optional
    # Settings for Launch Control builds only:
    os_type: brillo # Type of OS, e.g., cros, brillo, android. Default is
             cros. Required for android/brillo builds.
    branches: git_mnc_release # comma separated string of Launch Control
              branches. Required and only applicable for android/brillo
              builds.
    targets: dragonboard-eng # comma separated string of build targets.
             Required and only applicable for android/brillo builds.
    testbed_dut_count: Number of duts to test when using a testbed.

    By default, Tasks run on all release branches, not factory or firmware.

    Args:
      section: the section to parse into a Task.

    Returns:
      A task.Task object.

    Raises:
      MalformedConfigEntryError: if there's a problem parsing |section|.
    """
    if not self._config_reader.has_section(section):
      raise MalformedConfigEntryError('unknown section %s' % section)

    section_headers = self._ALLOWED_HEADER.union(
        dict(self._config_reader.items(section)).keys())
    extra_keys = section_headers.difference(self._ALLOWED_HEADER)
    if self._ALLOWED_HEADER != section_headers:
      raise MalformedConfigEntryError(
          '%s: unknown entries: %s' % (section, ', '.join(extra_keys)))

    task_info = self._read_task_section(section)
    self._validate_task_section(task_info)

    return task.Task(
        task_info,
        board_family_config=self._board_family_config,
        tot=self._tot_manager,
        is_sanity=self.is_sanity)
