# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module of config file readers."""

import ConfigParser
import collections
import logging
import re

import build_lib
import task
import time_converter
import timed_event
import tot_manager
import build_event

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

# Namedtuple for storing db info.
DBInfo = collections.namedtuple(
    'DBConfigs',
    [
        'connection_name',
        'user',
        'password',
    ])

# Common task entries
CommonTaskEntries = ['boards',
                     'branch_specs',
                     'cros_build_spec',
                     'day',
                     'file_bugs',
                     'firmware_ro_build_spec',
                     'firmware_rw_build_spec',
                     'hour',
                     'job_retry',
                     'lc_branches',
                     'lc_targets',
                     'no_delay',
                     'num',
                     'os_type',
                     'pool',
                     'priority',
                     'suite',
                     'test_source',
                     'timeout']

# Namedtuple for storing task info.
TaskInfo = collections.namedtuple(
    'TaskInfo',
    CommonTaskEntries + ['name', 'keyword', 'testbed_dut_count']
    )

class MalformedConfigEntryError(Exception):
    """Raised to indicate a config parsing failure."""


def forgive_config_error(func):
    """A decorator making ConfigParser get*() functions return None on fail."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ConfigParser.Error:
            return None

    return wrapper


class ConfigReader(ConfigParser.SafeConfigParser):
    """A SafeConfigReader that returns None on any error in get*().

    TODO(xixuan): This config_reader uses ConfigParser class to read config
    file. This config format could be replaced by other more expressive ones.
    """

    def __init__(self, filename):
        """Initialize a config reader."""
        ConfigParser.SafeConfigParser.__init__(self)
        self.read(filename)

    def read(self, filename):
        """Read the file indicated by the given filename.

        Args:
            filename: string for the file name to read.
        """
        self.filename = filename
        ConfigParser.SafeConfigParser.read(self, filename)

    @forgive_config_error
    def getstring(self, section, option):
        """Get string value for the given section and option."""
        return ConfigParser.SafeConfigParser.get(self, section, option)

    @forgive_config_error
    def getint(self, section, option):
        """Get int value for the given section and option."""
        return ConfigParser.SafeConfigParser.getint(self, section, option)

    @forgive_config_error
    def getfloat(self, section, option):
        """Get float value for the given section and option."""
        return ConfigParser.SafeConfigParser.getfloat(self, section, option)

    @forgive_config_error
    def getboolean(self, section, option):
        """Get boolean value for the given section and option."""
        return ConfigParser.SafeConfigParser.getboolean(self, section, option)


class TaskConfig(object):
    """Class for reading task config file for suite scheduler."""

    _ALLOWED_HEADER = set(CommonTaskEntries + ['owner', 'run_on'])

    def __init__(self, config_reader):
        """Initialize a TaskConfig to generate task list from config file.

        Args:
            config_reader: a ConfigReader object to read task config.
            filename: task config file name.
        """
        self._config_reader = config_reader
        self._tot_manager = tot_manager.TotMilestoneManager()

    def get_tasks_by_keyword(self, event_type):
        """Obtain tasks from config sections read from config file.

        Args:
            event_type: the event_type for the tasks to fetch,
                like 'new_build'.

        Returns:
            a list of task.Task objects.
        """
        tasks = []
        for section in self._config_reader.sections():
            if event_type == self._get_keyword(section):
                try:
                    new_task = self._create_task_from_config_section(section)
                    tasks.append(new_task)
                except MalformedConfigEntryError as e:
                    logging.exception(str(e))
                    continue

        return tasks

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
        return self._config_reader.getstring(section, 'run_on')

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
        keyword = self._config_reader.getstring(section, 'run_on')
        suite = self._config_reader.getstring(section, 'suite')
        pool = self._config_reader.getstring(section, 'pool')
        boards = self._config_reader.getstring(section, 'boards')
        cros_build_spec = self._config_reader.getstring(
            section, 'cros_build_spec')
        firmware_rw_build_spec = self._config_reader.getstring(
            section, 'firmware_rw_build_spec')
        firmware_ro_build_spec = self._config_reader.getstring(
            section, 'firmware_ro_build_spec')
        test_source = self._config_reader.getstring(section, 'test_source')
        lc_branches = self._config_reader.getstring(section, 'lc_branches')
        lc_targets = self._config_reader.getstring(section, 'lc_targets')
        branch_specs = self._config_reader.getstring(section, 'branch_specs')
        if branch_specs is not None:
            branch_specs = re.split('\s*,\s*', branch_specs)

        os_type = self._config_reader.getstring(section, 'os_type')
        os_type = build_lib.OS_TYPE_CROS if os_type is None else os_type

        job_retry = self._config_reader.getboolean(section, 'job_retry')
        job_retry = False if job_retry is None else job_retry

        file_bugs = self._config_reader.getboolean(section, 'file_bugs')
        file_bugs = False if file_bugs is None else file_bugs

        no_delay = self._config_reader.getboolean(section, 'no_delay')
        no_delay = False if no_delay is None else no_delay

        priority = self._config_reader.getint(section, 'priority')
        if priority is None:
            priority = EVENT_CLASSES[keyword].PRIORITY

        timeout = self._config_reader.getint(section, 'timeout')
        if timeout is None:
            timeout = EVENT_CLASSES[keyword].TIMEOUT

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
            raise MalformedConfigEntryError("Ill-specified |day|: %s" % e)

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

        return TaskInfo(name=section,
                        keyword=keyword,
                        suite=suite,
                        pool=pool,
                        boards=boards,
                        priority=priority,
                        timeout=timeout,
                        file_bugs=file_bugs,
                        job_retry=job_retry,
                        no_delay=no_delay,
                        num=num,
                        hour=hour,
                        day=day,
                        branch_specs=branch_specs,
                        cros_build_spec=cros_build_spec,
                        firmware_ro_build_spec=firmware_ro_build_spec,
                        firmware_rw_build_spec=firmware_rw_build_spec,
                        test_source=test_source,
                        lc_branches=lc_branches,
                        lc_targets=lc_targets,
                        os_type=os_type,
                        testbed_dut_count=testbed_dut_count)

    def _validate_task_section(self, task_info):
        """Validate a task section.

        Args:
            task_info: a TaskInfo object.

        Raises:
            MalformedConfigEntryError if any item in section is not valid.
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

        if task_info.hour is not None and task_info.keyword != 'nightly':
            raise MalformedConfigEntryError(
                '%s: |hour| represents a timepoint of a day, that can '
                'only apply to nightly event.' % task_info.name)

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
        boards: board1, board2  # comma seperated string, Optional
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
            MalformedConfigEntryError if there's a problem parsing |section|.
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
            section,
            task_info.suite,
            task_info.branch_specs,
            task_info.pool,
            task_info.num,
            task_info.boards,
            task_info.priority,
            task_info.timeout,
            file_bugs=task_info.file_bugs,
            cros_build_spec=task_info.cros_build_spec,
            firmware_rw_build_spec=task_info.firmware_rw_build_spec,
            firmware_ro_build_spec=task_info.firmware_ro_build_spec,
            test_source=task_info.test_source,
            job_retry=task_info.job_retry,
            no_delay=task_info.no_delay,
            hour=task_info.hour,
            day=task_info.day,
            os_type=task_info.os_type,
            launch_control_branches=task_info.lc_branches,
            launch_control_targets=task_info.lc_targets,
            testbed_dut_count=task_info.testbed_dut_count,
            tot_manager=self._tot_manager)


class LabConfig(object):
    """Class for reading lab config file for suite scheduler."""

    def __init__(self, config_reader):
        """Initialize a LabConfig to read lab info.

        Args:
            config_reader: a config reader to read task config.
            filename: task config file name.
        """
        self._config_reader = config_reader

    def get_android_board_list(self):
        """Get the android board list from lab config file.

        Returns:
            A set of Android boards: (android-angler, android-bullhead, ...)
        """
        board_list = self._config_reader.getstring(
            _ANDROID_BOARD, 'board_list').split(',')
        return set([re.match(r'(.*?)(?:-\d+)?$', board.strip()).group(1)
                    for board in board_list])

    def get_firmware_ro_build_list(self, release_board):
        """Get firmware ro build list from config file.

        Args:
            release_board: The format like RELEASED_RO_BUILDS_[board].

        Returns:
            a string contains released_ro_builds split by comma.

        Raises:
            ValueError if no firmware_ro_build found.
        """
        board_list = self._config_reader.getstring(
            _RELEASED_RO_BUILDS, release_board)
        if board_list is None:
            raise ValueError('No firmware ro build list found for %s' %
                             release_board)

        return board_list


class DBConfig(object):
    """Class for reading db config file for suite scheduler."""

    def __init__(self, config_reader):
        """Initialize a DBConfig to read db info.

        Args:
            config_reader: a config reader to read task config.
            filename: task config file name.
        """
        self._config_reader = config_reader

    def get_credentials(self, db_tag):
        """Get cidb connection name/user/passwd.

        Args:
            db_tag: the section to read credentials.

        Returns:
            A DBInfo object.
        """
        return DBInfo(
            connection_name=self._config_reader.getstring(
                db_tag, 'connection_name'),
            user=self._config_reader.getstring(db_tag, 'user'),
            password=self._config_reader.getstring(db_tag, 'password'))


# The regex for testbed dut count
_TESTBED_DUT_COUNT_REGEX = '[^,]*-(\d+)'

# The entries for lab config files
_ANDROID_BOARD = 'AndroidBoard'
_RELEASED_RO_BUILDS = 'RELEASED_RO_BUILDS'
