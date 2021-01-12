# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for task config reader unittests."""
# pylint: disable=g-missing-super-call

import unittest

import config_reader
import constants
import mock
import task_config_reader
import tot_manager


class FakeTotMilestoneManager(tot_manager.TotMilestoneManager):

  def __init__(self, is_sanity):
    self.is_sanity = is_sanity
    self.storage_client = None
    self.tot = self._tot_milestone()


class BaseTaskConfigReaderTestCase(unittest.TestCase):

  _EVENT_TYPE = 'nightly'
  _PRIORITY = task_config_reader.EVENT_CLASSES[_EVENT_TYPE].PRIORITY
  _TIMEOUT = task_config_reader.EVENT_CLASSES[_EVENT_TYPE].TIMEOUT
  _TASK_NAME = 'fake_task'
  _SUITE = 'fake_suite'
  _BRANCH_SPEC = 'tot-1'
  _POOL = 'bvt'
  _NUM = 2
  _BOARD = 'link'
  _DIMENSIONS = 'label-wifi:foo'

  def setUp(self):
    self.config = config_reader.ConfigReader(None)
    self.config.add_section(self._TASK_NAME)
    self.config.set(self._TASK_NAME, 'suite', self._SUITE)
    self.config.set(self._TASK_NAME, 'branch_specs', self._BRANCH_SPEC)
    self.config.set(self._TASK_NAME, 'run_on', self._EVENT_TYPE)
    self.config.set(self._TASK_NAME, 'pool', self._POOL)
    self.config.set(self._TASK_NAME, 'num', '%d' % self._NUM)
    self.config.set(self._TASK_NAME, 'boards', self._BOARD)
    self.config.set(self._TASK_NAME, 'dimensions', self._DIMENSIONS)

    tot_patcher = mock.patch('tot_manager.TotMilestoneManager')
    self._tot = tot_patcher.start()
    self._tot.return_value = FakeTotMilestoneManager(True)

    board_family_patcher = mock.patch(
        'build_lib.get_board_family_mapping_from_gs')
    board_family_getter = board_family_patcher.start()
    board_family_getter.return_value = {
        'nyan': ['nyan', 'nyan_blaze', 'nyan_big'],
        'ivybridge': ['link', 'link_freon']}

    self.addCleanup(tot_patcher.stop)
    self.addCleanup(board_family_patcher.stop)


class TaskCreationTestCase(BaseTaskConfigReaderTestCase):

  def testCreateTaskFromConfigNonexistentSection(self):
    """Ensure a Task CANNOT be built without suite, and raise error."""
    task_config = task_config_reader.TaskConfig(self.config)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._create_task_from_config_section,
                      'non-existent section')

  def testCreateTaskFromConfigNotAllowedHeader(self):
    """Ensure a Task can be built with unknown config headers."""
    self.config.set(self._TASK_NAME, 'non-valid-header', 'test')
    task_config = task_config_reader.TaskConfig(self.config)
    response = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertEqual(len(response), 1)

  def testGetTaskByKeyword(self):
    """Ensure a Task can be built from a correct config."""
    task_config = task_config_reader.TaskConfig(self.config)
    tasks = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertEqual(len(tasks), 1)
    new_task = tasks[0]
    self.assertEqual(new_task.name, self._TASK_NAME)
    self.assertEqual(new_task.suite, self._SUITE)
    self.assertEqual(new_task.branch_specs, [self._BRANCH_SPEC])
    self.assertEqual(new_task.pool, self._POOL)
    self.assertEqual(new_task.num, self._NUM)
    self.assertEqual(new_task.boards,
                     [t.lstrip() for t in self._BOARD.split(',')])
    self.assertEqual(new_task.priority, self._PRIORITY)
    self.assertEqual(new_task.timeout, self._TIMEOUT)
    self.assertEqual(new_task.dimensions, self._DIMENSIONS)

  def testGetTaskByKeywordNoRunonNoRaise(self):
    """Ensure a Task CANNOT be built without run_on, but not raise error."""
    self.config.remove_option(self._TASK_NAME, 'run_on')
    task_config = task_config_reader.TaskConfig(self.config)
    try:
      response = task_config.get_tasks_by_keyword(self._EVENT_TYPE)
      self.assertEqual(len(response['tasks']), 0)
      self.assertEqual(len(response['exceptions']), 1)
    except task_config_reader.MalformedConfigEntryError:
      self.fail('task_config should not raise error without run_on!')

  def testGetTaskByKeywordNoSuiteNoRaise(self):
    """Ensure a Task CANNOT be built without suite, but not raise error.

    This is to ensure a malformed task won't affect other tasks' reading.
    """
    self.config.remove_option(self._TASK_NAME, 'suite')
    task_config = task_config_reader.TaskConfig(self.config)
    try:
      response = task_config.get_tasks_by_keyword(self._EVENT_TYPE)
      self.assertEqual(len(response['tasks']), 0)
      self.assertEqual(len(response['exceptions']), 1)
    except config_reader.MalformedConfigEntry:
      self.fail('task_config should not raise error without suite!')

  def testGetTaskByKeywordNoBranch(self):
    """Ensure a Task can be built without branch_specs."""
    self.config.remove_option(self._TASK_NAME, 'branch_specs')
    task_config = task_config_reader.TaskConfig(self.config)
    tasks = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertEqual(tasks[0].branch_specs, [])

  def testGetTaskByKeywordNoNum(self):
    """Ensure a Task can be built without num."""
    self.config.remove_option(self._TASK_NAME, 'num')
    task_config = task_config_reader.TaskConfig(self.config)
    tasks = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertIsNone(tasks[0].num)

  def testSetPriority(self):
    """Ensure priority can be set by user."""
    priority = constants.Priorities.DEFAULT
    self.config.set(self._TASK_NAME, 'priority', str(priority))
    task_config = task_config_reader.TaskConfig(self.config)
    tasks = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertEqual(tasks[0].priority, priority)

  def testSuitePoolShouldNotSetPriority(self):
    """Ensure priority is not set for pool suites."""
    self.config.set(self._TASK_NAME, 'pool', 'suites')
    task_config = task_config_reader.TaskConfig(self.config)
    tasks = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertIsNone(tasks[0].priority)

  def testSetTimeout(self):
    """Ensure timeout can be set by user."""
    timeout = 1000
    self.config.set(self._TASK_NAME, 'timeout', str(timeout))
    task_config = task_config_reader.TaskConfig(self.config)
    tasks = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertEqual(tasks[0].timeout, timeout)


class TaskInfoCheckTestCase(BaseTaskConfigReaderTestCase):

  def testNonIntNum(self):
    """Ensure a Task's num is a Integer."""
    self.config.set(self._TASK_NAME, 'num', 'non_int')
    task_config = task_config_reader.TaskConfig(self.config)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._read_task_section,
                      self._TASK_NAME)

  def testNonIntHour(self):
    """Ensure a Task's hour is a Integer."""
    self.config.set(self._TASK_NAME, 'hour', 'non_int')
    task_config = task_config_reader.TaskConfig(self.config)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._read_task_section,
                      self._TASK_NAME)

  def testNonIntDay(self):
    """Ensure a Task's hour is a Integer."""
    self.config.set(self._TASK_NAME, 'day', 'non_int')
    task_config = task_config_reader.TaskConfig(self.config)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._read_task_section,
                      self._TASK_NAME)

  def testNoSuite(self):
    """Ensure a Task's suite exists."""
    self.config.remove_option(self._TASK_NAME, 'suite')
    task_config = task_config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._validate_task_section,
                      task_info)

  def testInvalidIntHour(self):
    """Ensure a Task's hour is in 0~23."""
    self.config.set(self._TASK_NAME, 'hour', '24')
    task_config = task_config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._validate_task_section,
                      task_info)

  def testNoHourForNonNightlyEvent(self):
    """Ensure a non-nightly Task cannot specify hour."""
    self.config.set(self._TASK_NAME, 'hour', '10')
    self.config.set(self._TASK_NAME, 'run_on', 'new_build')
    task_config = task_config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._validate_task_section,
                      task_info)

  def testInvalidIntDay(self):
    """Ensure a Task's day is in 0~6."""
    self.config.set(self._TASK_NAME, 'day', '10')
    self.config.set(self._TASK_NAME, 'run_on', 'weekly')
    task_config = task_config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._validate_task_section,
                      task_info)

  def testNoDayForNonWeeklyEvent(self):
    """Ensure a non-weekly Task cannot specify day."""
    self.config.set(self._TASK_NAME, 'day', '1')
    self.config.set(self._TASK_NAME, 'run_on', 'nightly')
    task_config = task_config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._validate_task_section,
                      task_info)

  def testInValidOSType(self):
    """Ensure a Task's os_type is valid."""
    self.config.set(self._TASK_NAME, 'os_type', 'invalid')
    task_config = task_config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._check_os_type,
                      task_info)

  def testNoLaunchControlForCrOS(self):
    """Ensure a CrOS Task doesn't have launch control settings."""
    self.config.set(self._TASK_NAME, 'os_type', 'CrOS')
    self.config.set(self._TASK_NAME, 'branches', 'shamu-userdebug')
    task_config = task_config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._check_os_type,
                      task_info)

  def testLaunchControlForNonCrOS(self):
    """Ensure an android Task has launch control settings."""
    self.config.set(self._TASK_NAME, 'os_type', 'android')
    task_config = task_config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._check_os_type,
                      task_info)

  def testGetTestbedCount(self):
    """Ensure testbed count can be successfully parsed."""
    task_config = task_config_reader.TaskConfig(self.config)
    self.assertEqual(task_config._get_testbed_dut_count('sharu-2'), 2)

  def testNoTestbedForCrOS(self):
    """Ensure CrOS task won't specify testbed parameters."""
    self.config.set(self._TASK_NAME, 'boards', 'sharu-2')
    task_config = task_config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._check_testbed_parameter,
                      task_info)

  def testInvalidBoardFamilies(self):
    """Ensure to raise exception when a board family is invalid."""
    self.config.set(self._TASK_NAME, 'board_families', 'fake_one')
    task_config = task_config_reader.TaskConfig(self.config)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._read_task_section,
                      self._TASK_NAME)

  def testInvalidExcludeBoardFamilies(self):
    """Ensure to raise exception when an exclude board family is invalid."""
    self.config.set(self._TASK_NAME, 'exclude_board_families', 'fake_one')
    task_config = task_config_reader.TaskConfig(self.config)
    self.assertRaises(task_config_reader.MalformedConfigEntryError,
                      task_config._read_task_section,
                      self._TASK_NAME)
