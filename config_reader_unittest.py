# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for config reader unittests."""

import unittest

import config_reader
import constants
import mock
import tot_manager


class FakeTotMilestoneManager(tot_manager.TotMilestoneManager):

  def __init__(self, is_sanity):
    self.is_sanity = is_sanity
    self.storage_client = None
    self.tot = self._tot_milestone()


class BaseTaskConfigReaderTestCase(unittest.TestCase):

  _EVENT_TYPE = 'nightly'
  _PRIORITY = config_reader.EVENT_CLASSES[_EVENT_TYPE].PRIORITY
  _TIMEOUT = config_reader.EVENT_CLASSES[_EVENT_TYPE].TIMEOUT
  _TASK_NAME = 'fake_task'
  _SUITE = 'fake_suite'
  _BRANCH_SPEC = 'tot-1'
  _POOL = 'bvt'
  _NUM = 2
  _BOARD = 'link'

  def setUp(self):
    self.config = config_reader.ConfigReader(None)
    self.config.add_section(self._TASK_NAME)
    self.config.set(self._TASK_NAME, 'suite', self._SUITE)
    self.config.set(self._TASK_NAME, 'branch_specs', self._BRANCH_SPEC)
    self.config.set(self._TASK_NAME, 'run_on', self._EVENT_TYPE)
    self.config.set(self._TASK_NAME, 'pool', self._POOL)
    self.config.set(self._TASK_NAME, 'num', '%d' % self._NUM)
    self.config.set(self._TASK_NAME, 'boards', self._BOARD)

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
    task_config = config_reader.TaskConfig(self.config)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._create_task_from_config_section,
                      'non-existent section')

  def testCreateTaskFromConfigNotAllowedHeader(self):
    """Ensure a Task CANNOT be built without suite, and raise error."""
    self.config.set(self._TASK_NAME, 'non-valid-header', 'test')
    task_config = config_reader.TaskConfig(self.config)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._create_task_from_config_section,
                      self._TASK_NAME)

  def testGetTaskByKeyword(self):
    """Ensure a Task can be built from a correct config."""
    task_config = config_reader.TaskConfig(self.config)
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

  def testGetTaskByKeywordNoRunonNoRaise(self):
    """Ensure a Task CANNOT be built without run_on, but not raise error."""
    self.config.remove_option(self._TASK_NAME, 'run_on')
    task_config = config_reader.TaskConfig(self.config)
    try:
      response = task_config.get_tasks_by_keyword(self._EVENT_TYPE)
      self.assertEqual(len(response['tasks']), 0)
      self.assertEqual(len(response['exceptions']), 1)
    except config_reader.MalformedConfigEntryError:
      self.fail('task_config should not raise error without run_on!')

  def testGetTaskByKeywordNoSuiteNoRaise(self):
    """Ensure a Task CANNOT be built without suite, but not raise error.

    This is to ensure a malformed task won't affect other tasks' reading.
    """
    self.config.remove_option(self._TASK_NAME, 'suite')
    task_config = config_reader.TaskConfig(self.config)
    try:
      response = task_config.get_tasks_by_keyword(self._EVENT_TYPE)
      self.assertEqual(len(response['tasks']), 0)
      self.assertEqual(len(response['exceptions']), 1)
    except config_reader.MalformedConfigEntry:
      self.fail('task_config should not raise error without suite!')

  def testGetTaskByKeywordNoBranch(self):
    """Ensure a Task can be built without branch_specs."""
    self.config.remove_option(self._TASK_NAME, 'branch_specs')
    task_config = config_reader.TaskConfig(self.config)
    tasks = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertEqual(tasks[0].branch_specs, [])

  def testGetTaskByKeywordNoNum(self):
    """Ensure a Task can be built without num."""
    self.config.remove_option(self._TASK_NAME, 'num')
    task_config = config_reader.TaskConfig(self.config)
    tasks = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertIsNone(tasks[0].num)

  def testSetPriority(self):
    """Ensure priority can be set by user."""
    priority = constants.Priorities.DEFAULT
    self.config.set(self._TASK_NAME, 'priority', str(priority))
    task_config = config_reader.TaskConfig(self.config)
    tasks = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertEqual(tasks[0].priority, priority)

  def testSetTimeout(self):
    """Ensure timeout can be set by user."""
    timeout = 1000
    self.config.set(self._TASK_NAME, 'timeout', str(timeout))
    task_config = config_reader.TaskConfig(self.config)
    tasks = task_config.get_tasks_by_keyword(self._EVENT_TYPE)['tasks']
    self.assertEqual(tasks[0].timeout, timeout)


class TaskInfoCheckTestCase(BaseTaskConfigReaderTestCase):

  def testNonIntNum(self):
    """Ensure a Task's num is a Integer."""
    self.config.set(self._TASK_NAME, 'num', 'non_int')
    task_config = config_reader.TaskConfig(self.config)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._read_task_section,
                      self._TASK_NAME)

  def testNonIntHour(self):
    """Ensure a Task's hour is a Integer."""
    self.config.set(self._TASK_NAME, 'hour', 'non_int')
    task_config = config_reader.TaskConfig(self.config)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._read_task_section,
                      self._TASK_NAME)

  def testNonIntDay(self):
    """Ensure a Task's hour is a Integer."""
    self.config.set(self._TASK_NAME, 'day', 'non_int')
    task_config = config_reader.TaskConfig(self.config)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._read_task_section,
                      self._TASK_NAME)

  def testNoSuite(self):
    """Ensure a Task's suite exists."""
    self.config.remove_option(self._TASK_NAME, 'suite')
    task_config = config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._validate_task_section,
                      task_info)

  def testInvalidIntHour(self):
    """Ensure a Task's hour is in 0~23."""
    self.config.set(self._TASK_NAME, 'hour', '24')
    task_config = config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._validate_task_section,
                      task_info)

  def testNoHourForNonNightlyEvent(self):
    """Ensure a non-nightly Task cannot specify hour."""
    self.config.set(self._TASK_NAME, 'hour', '10')
    self.config.set(self._TASK_NAME, 'run_on', 'new_build')
    task_config = config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._validate_task_section,
                      task_info)

  def testInvalidIntDay(self):
    """Ensure a Task's day is in 0~6."""
    self.config.set(self._TASK_NAME, 'day', '10')
    self.config.set(self._TASK_NAME, 'run_on', 'weekly')
    task_config = config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._validate_task_section,
                      task_info)

  def testNoDayForNonWeeklyEvent(self):
    """Ensure a non-weekly Task cannot specify day."""
    self.config.set(self._TASK_NAME, 'day', '1')
    self.config.set(self._TASK_NAME, 'run_on', 'nightly')
    task_config = config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._validate_task_section,
                      task_info)

  def testInValidOSType(self):
    """Ensure a Task's os_type is valid."""
    self.config.set(self._TASK_NAME, 'os_type', 'invalid')
    task_config = config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._check_os_type,
                      task_info)

  def testNoLaunchControlForCrOS(self):
    """Ensure a CrOS Task doesn't have launch control settings."""
    self.config.set(self._TASK_NAME, 'os_type', 'CrOS')
    self.config.set(self._TASK_NAME, 'branches', 'shamu-userdebug')
    task_config = config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._check_os_type,
                      task_info)

  def testLaunchControlForNonCrOS(self):
    """Ensure an android Task has launch control settings."""
    self.config.set(self._TASK_NAME, 'os_type', 'android')
    task_config = config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._check_os_type,
                      task_info)

  def testGetTestbedCount(self):
    """Ensure testbed count can be successfully parsed."""
    task_config = config_reader.TaskConfig(self.config)
    self.assertEqual(task_config._get_testbed_dut_count('sharu-2'), 2)

  def testNoTestbedForCrOS(self):
    """Ensure CrOS task won't specify testbed parameters."""
    self.config.set(self._TASK_NAME, 'boards', 'sharu-2')
    task_config = config_reader.TaskConfig(self.config)
    task_info = task_config._read_task_section(self._TASK_NAME)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._check_testbed_parameter,
                      task_info)

  def testInvalidBoardFamily(self):
    """Ensure to raise exception when a board family is invalid."""
    self.config.set(self._TASK_NAME, 'board_family', 'fake_one')
    task_config = config_reader.TaskConfig(self.config)
    self.assertRaises(config_reader.MalformedConfigEntryError,
                      task_config._read_task_section,
                      self._TASK_NAME)


class LabReaderTestCase(unittest.TestCase):

  def setUp(self):
    self.config = config_reader.ConfigReader(None)
    self.config.add_section(config_reader.ANDROID_SETTINGS)
    self.config.add_section(config_reader.CROS_SETTINGS)
    self.config.add_section(config_reader.RELEASED_RO_BUILDS)

  def testGetAndroidBoardList(self):
    """Ensure android board list can be correctly fetched."""
    self.config.set(config_reader.ANDROID_SETTINGS, 'board_list',
                    '\nabox_edge,\nandroid-angler-1,\nangler-6')
    lab_config = config_reader.LabConfig(self.config)
    self.assertEqual(lab_config.get_android_board_list(),
                     set(['abox_edge', 'android-angler', 'angler']))

  def testGetInvalidAndroidBoardListEntry(self):
    """Ensure ValueError is raised if no valid board list entry."""
    self.config.set(config_reader.ANDROID_SETTINGS, 'invalid_board_list',
                    '\nabox_edge,\nandroid-angler-1,\nangler-6')
    lab_config = config_reader.LabConfig(self.config)
    self.assertRaises(ValueError, lab_config.get_android_board_list)

  def testGetEmptyAndroidBoardListEntry(self):
    """Ensure ValueError is raised if no android board list is found."""
    lab_config = config_reader.LabConfig(self.config)
    self.assertRaises(ValueError, lab_config.get_android_board_list)

  def testGetCrOSBoardList(self):
    """Ensure android board list can be correctly fetched."""
    self.config.set(config_reader.CROS_SETTINGS, 'board_list',
                    '\nlink,\nandroid-angler-1,\nangler-6')
    self.config.set(config_reader.ANDROID_SETTINGS, 'board_list',
                    '\nandroid-angler-1,\nangler-6')
    lab_config = config_reader.LabConfig(self.config)
    self.assertEqual(lab_config.get_cros_board_list(),
                     set(['link']))

  def testGetFirmwareROBuildList(self):
    """Ensure firmware ro build can be successfully found."""
    self.config.set(config_reader.RELEASED_RO_BUILDS, 'link', 'firmware')
    lab_config = config_reader.LabConfig(self.config)
    self.assertEqual(lab_config.get_firmware_ro_build_list('link'),
                     'firmware')

  def testGetEmptyFirmwareROBuildList(self):
    """Ensure ValueError is raised if no firmware ro build is found."""
    lab_config = config_reader.LabConfig(self.config)
    self.assertRaises(ValueError,
                      lab_config.get_firmware_ro_build_list, 'link')

  def testGetCrOSModelMap(self):
    """Ensure cros_model_map can be correctly fetched."""
    self.config.set(config_reader.CROS_SETTINGS, 'model_list',
                    '\ncoral_astronaut,\ncoral_robo360')
    lab_config = config_reader.LabConfig(self.config)
    result = lab_config.get_cros_model_map()
    self.assertEqual(len(result), 1)
    self.assertEqual(result['coral'], ['astronaut', 'robo360'])

  def testGetEmptyCrOSModelMap(self):
    """Ensure cros_model_map can be correctly fetched."""
    lab_config = config_reader.LabConfig(self.config)
    self.assertEqual(lab_config.get_cros_model_map(), {})


if __name__ == '__main__':
  unittest.main()
