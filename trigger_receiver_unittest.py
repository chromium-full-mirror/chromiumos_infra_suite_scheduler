# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for trigger_receiver unittests."""
# pylint: disable=g-missing-super-call

import datetime
import os
import unittest

import build_lib
import config_reader
import datastore_client
import file_getter
import mock
import task_config_reader
import task_executor
import time_converter
import trigger_receiver

from google.appengine.api import taskqueue
from google.appengine.ext import ndb
from google.appengine.ext import testbed

# Ensure that SUITE_SCHEDULER_CONFIG_FILE is read only once.
_SUITE_CONFIG_READER = config_reader.ConfigReader(
    file_getter.TEST_SUITE_SCHEDULER_CONFIG_FILE)


def now_generator(start_time, interval_min=30, last_days=7):
  """A datetime.datetime.now generator.

  The generator will generate 'now' from start_time till start_time+last_days
  for every interval_min.

  Args:
    start_time: A datetime.datetime object representing the initial value of
      the 'now'.
    interval_min: The interval minutes between current 'now' and next 'now.
    last_days: Representing how many days this generator will last.

  Yields:
    a datetime.datetime object to mock the current time.
  """
  cur_time = start_time
  end_time = start_time + datetime.timedelta(days=last_days)
  while cur_time < end_time:
    yield cur_time
    cur_time += datetime.timedelta(minutes=interval_min)


def _should_schedule_timed_task(last_now, now):
  """Check whether timed (weekly/nightly) task should be scheduled.

  A timed task should be schduled when next hour is coming.

  Args:
    last_now: the last time to check if timed task should be scheduled
      or not.
    now: the current time to check if timed task should be scheduled.

  Returns:
    a boolean indicating whether there will be nightly tasks scheduled.
  """
  if last_now is not None and last_now.hour != now.hour:
    return True

  return False


def _should_schedule_new_build_task(last_now, now):
  """Check whether weekly task should be scheduled.

  A new_build task should be schduled when there're new builds between last
  check and this check.

  Args:
    last_now: the last time to check if new_build task should be scheduled.
    now: the current time to check if new_build task should be scheduled.

  Returns:
    a boolean indicating whether there will be new_build tasks scheduled.
  """
  if last_now is not None and last_now != now:
    return True

  return False


class FakeBuildClient(object):
  """Mock rest_client.BuildBucketBigqueryClient."""

  def __init__(self):
    self.firmware_builds_called = 0

  def get_passed_builds(self, earliest, latest):
    """Mock get_passed_builds."""
    del earliest  # unused
    del latest # unused
    return [
        build_lib.BuildInfo(
            'link', None, '62', '9868.0.0', 'link-release'),
        build_lib.BuildInfo(
            'zako', None, '62', '9868.0.0', 'zako-release'),
        build_lib.BuildInfo('samus-kernelnext', None, '62',
                            '9868.0.0', 'samus-kernelnext-release'),
        build_lib.BuildInfo(
            'reef', None, '62', '1234.0.0', 'reef-release'),
        build_lib.BuildInfo(
            'coral', 'santa', '62', '9868.0.0', 'coral-release'),
        build_lib.BuildInfo(
            'coral', 'astronaut', '62', '9868.0.0', 'coral-release'),
        build_lib.BuildInfo(
            'coral', 'lava', '62', '9868.0.0', 'coral-release'),
    ]

  def get_latest_passed_builds(self, build_config):
    """Mock get_latest_passed_builds."""
    del build_config  # unused
    return build_lib.BuildInfo('link', '62', '9868.0.0', build_config)

  def get_relaxed_passed_builds(self, earliest, latest):
    """Mock get_relaxed_pased_builds."""
    del earliest  # unused
    del latest # unused
    return [
        build_lib.BuildInfo('grunt', None, '63', '9968.0.0', 'grunt-release'),
        build_lib.BuildInfo('nami', None, '62', '9867.0.0', 'nami-release'),
        build_lib.BuildInfo('nami', 'akali', '62', '9868.0.0', 'nami-release'),
        build_lib.BuildInfo('nami', 'bard', '62', '9866.0.0', 'nami-release'),
    ]

  def get_latest_passed_firmware_builds(self):
    """Mock get_passed_firmware_builds."""
    self.firmware_builds_called += 1
    return [
        ['cros', 'fake_board', ('gs://chromeos-image-archive/'
                                'fake_board-release/R30-6182.0.0-rc2/'
                                'fake_board')],
        ['firmware', 'fake_board', ('gs://chromeos-image-archive/'
                                    'firmware-fake_board-12345.67.'
                                    'A-firmwarebranch/RFoo-1.0.0-b1e234567')],
        ['firmware', 'zako', ('gs://chromeos-image-archive/'
                              'firmware-zako-12345.67.'
                              'A-firmwarebranch/RFoo-1.0.0-b1e234567')],
    ]


class FakeAndroidBuildRestClient(object):
  """Mock rest_client.AndroidBuildRestClient."""

  def get_latest_build_id(self, branch, target):
    """Mock rest_client.AndroidBuildRestClient.get_latest_build_id."""
    del branch, target  # unused
    return '100'


class FakeLabConfig(object):
  """Mock config_reader.LabConfig."""

  def get_android_board_list(self):
    """Mock config_reader.LabConfig.get_android_board_list."""
    return ('android-angler', 'android-bullhead')

  def get_cros_board_list(self):
    """Mock config_reader.LabConfig.get_cros_board_list."""
    return ('grunt', 'link', 'peppy', 'daisy', 'zako', 'samus-kernelnext',
            'coral', 'reef', 'nami')

  def get_firmware_ro_build_list(self, release_board):
    """Mock config_reader.LabConfig.get_firmware_ro_build_list."""
    del release_board  # unused
    return 'firmware1,firmware2'

  def get_cros_model_map(self):
    """Mock config_reader.LabConfig.get_cros_model_map."""
    return {
        'coral': ['santa', 'astronaut'],
        'reef': ['electro'],
        'nami': ['akali', 'bard'],
    }


class TriggerReceiverBaseTestCase(unittest.TestCase):

  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.addCleanup(self.testbed.deactivate)

    self.testbed.init_datastore_v3_stub()
    self.testbed.init_memcache_stub()
    ndb.get_context().clear_cache()
    self.testbed.init_taskqueue_stub(
        root_path=os.path.join(os.path.dirname(__file__)))
    self.taskqueue_stub = self.testbed.get_stub(
        testbed.TASKQUEUE_SERVICE_NAME)

    mock_build_client = mock.patch('rest_client.BuildBucketBigqueryClient')
    self._mock_build_client = mock_build_client.start()
    self.addCleanup(mock_build_client.stop)

    mock_android_client = mock.patch('rest_client.AndroidBuildRestClient')
    self._mock_android_client = mock_android_client.start()
    self.addCleanup(mock_android_client.stop)

    mock_lab_config = mock.patch('config_reader.LabConfig')
    self._mock_lab_config = mock_lab_config.start()
    self.addCleanup(mock_lab_config.stop)

    mock_utc_now = mock.patch('time_converter.utc_now')
    self._mock_utc_now = mock_utc_now.start()
    self.addCleanup(mock_utc_now.stop)

    self._mock_build_client.return_value = FakeBuildClient()
    self._mock_android_client.return_value = FakeAndroidBuildRestClient()
    self._mock_lab_config.return_value = FakeLabConfig()

    board_family_patcher = mock.patch(
        'build_lib.get_board_family_mapping_from_gs')
    board_family_getter = board_family_patcher.start()
    board_family_getter.return_value = {
        'nyan': ['nyan', 'nyan_blaze', 'nyan_big'],
        'ivybridge': ['link', 'link_freon']}
    self.addCleanup(board_family_patcher.stop)


class TriggerReceiverFakeConfigTestCase(TriggerReceiverBaseTestCase):

  _TEST_PST_HOUR = 20
  _TEST_PST_DAY = 4  # Friday
  _TEST_EVENT_PST_HOUR = 13

  _FAKE_NIGHTLY_TASK_NAME = 'fake_nightly_task'
  _FAKE_WEEKLY_TASK_NAME = 'fake_weekly_task'

  def setUp(self):
    super(TriggerReceiverFakeConfigTestCase, self).setUp()

    self.fake_config = config_reader.ConfigReader(None)
    self._add_nightly_tasks(self.fake_config)
    self._add_weekly_tasks(self.fake_config)

    self.fake_config_with_settings = config_reader.ConfigReader(None)
    self._add_weekly_tasks(self.fake_config_with_settings)
    self._add_weekly_params(self.fake_config_with_settings)

    mock_config_reader = mock.patch('config_reader.ConfigReader')
    self._mock_config_reader = mock_config_reader.start()
    self.addCleanup(mock_config_reader.stop)

  def _add_nightly_tasks(self, fake_config):
    fake_config.add_section(self._FAKE_NIGHTLY_TASK_NAME)
    fake_config.set(self._FAKE_NIGHTLY_TASK_NAME, 'suite', 'fake_suite')
    fake_config.set(self._FAKE_NIGHTLY_TASK_NAME, 'run_on', 'nightly')
    fake_config.set(self._FAKE_NIGHTLY_TASK_NAME, 'hour',
                    str(self._TEST_PST_HOUR))

  def _add_weekly_tasks(self, fake_config):
    fake_config.add_section(self._FAKE_WEEKLY_TASK_NAME)
    fake_config.set(self._FAKE_WEEKLY_TASK_NAME, 'suite', 'fake_suite')
    fake_config.set(self._FAKE_WEEKLY_TASK_NAME, 'run_on', 'weekly')
    fake_config.set(self._FAKE_WEEKLY_TASK_NAME, 'day', str(self._TEST_PST_DAY))

  def _add_weekly_params(self, fake_config):
    weekly_section_name = task_config_reader.EVENT_CLASSES[
        'weekly'].section_name()
    fake_config.add_section(weekly_section_name)
    fake_config.set(weekly_section_name, 'hour', str(self._TEST_EVENT_PST_HOUR))

  def testInitializeTriggerReceiverWithNightlyEvent(self):
    """Test nightly event can be handled on right hour."""
    # A task with hour=20 should be scheduled at 20:00 in PST everyday, which
    # is 3:00/4:00 in UTC everyday.
    self._mock_config_reader.return_value = self.fake_config
    given_utc_hour = time_converter.convert_time_info(
        time_converter.TimeInfo(None, self._TEST_PST_HOUR)).hour
    utc_now = datetime.datetime(2017, 8, 6, given_utc_hour,
                                tzinfo=time_converter.UTC_TZ)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        'nightly', utc_now - datetime.timedelta(hours=1))
    self._mock_utc_now.return_value = utc_now

    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()
    self.assertTrue(suite_trigger.events['nightly'].should_handle)
    self.assertEqual(len(suite_trigger.event_results['nightly']), 1)
    self.assertEqual(suite_trigger.event_results['nightly'][0],
                     self._FAKE_NIGHTLY_TASK_NAME)

  def testInitializeTriggerReceiverWithWeeklyEventWithoutEventHour(self):
    """Test weekly event without event settings can be handled on right day."""
    # A task with day=4 (Friday) and default event_hour (23) should be
    # scheduled at Friday 23:00 in PST, which is Saturday 6:00 or 7:00 in UTC.
    self._mock_config_reader.return_value = self.fake_config
    given_utc_hour = time_converter.convert_time_info(
        time_converter.TimeInfo(
            self._TEST_PST_DAY,
            task_config_reader.EVENT_CLASSES['weekly'].DEFAULT_PST_HOUR)).hour
    utc_now = datetime.datetime(2017, 10, 14, given_utc_hour,
                                tzinfo=time_converter.UTC_TZ)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        'weekly', utc_now - datetime.timedelta(days=1))
    self._mock_utc_now.return_value = utc_now

    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()
    self.assertTrue(suite_trigger.events['weekly'].should_handle)
    self.assertEqual(len(suite_trigger.event_results['weekly']), 1)
    self.assertEqual(suite_trigger.event_results['weekly'][0],
                     self._FAKE_WEEKLY_TASK_NAME)

  def testInitializeTriggerReceiverWithWeeklyEventWithEventHour(self):
    """Test weekly event with event settings can be handled on right day."""
    # A task with day=4 (Friday) and event_hour=13 should be scheduled at
    # Friday 13:00 in PST, which is Friday 20:00 or 21:00 in UTC.
    self._mock_config_reader.return_value = self.fake_config_with_settings
    given_utc_time_info = time_converter.convert_time_info(
        time_converter.TimeInfo(self._TEST_PST_DAY, self._TEST_EVENT_PST_HOUR))

    # Set the current time as a Friday 20:00 or 21:00 in UTC.
    utc_now = datetime.datetime(2017, 10, 13, given_utc_time_info.hour,
                                tzinfo=time_converter.UTC_TZ)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        'weekly', utc_now - datetime.timedelta(days=1))
    self._mock_utc_now.return_value = utc_now

    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()
    self.assertTrue(suite_trigger.events['weekly'].should_handle)
    self.assertEqual(len(suite_trigger.event_results['weekly']), 1)
    self.assertEqual(suite_trigger.event_results['weekly'][0],
                     self._FAKE_WEEKLY_TASK_NAME)


class TriggerReceiverFakeBuildTestCase(TriggerReceiverBaseTestCase):
  """Test the new_build functionality."""

  def setUp(self):
    """Set up for a test."""
    super(TriggerReceiverFakeBuildTestCase, self).setUp()

    self._prepare()

  def _prepare(self):
    self.fake_config = config_reader.ConfigReader(None)
    mock_config_reader = mock.patch('config_reader.ConfigReader')
    self._mock_config_reader = mock_config_reader.start()
    self.addCleanup(mock_config_reader.stop)

    # Set last execution time for new_build events.
    utc_now = datetime.datetime.now(time_converter.UTC_TZ)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        'new_build', utc_now - datetime.timedelta(hours=1))
    self._mock_utc_now.return_value = utc_now

  def testNewBuildForHWTestSanityRequired(self):
    """Test the new_build functionality."""
    # Construct a fake config with only_hwtest_sanity_required.
    fsnbt_name = 'FakeStrictNewBuildTask'
    self.fake_config.add_section(fsnbt_name)
    self.fake_config.set(fsnbt_name, 'run_on', 'new_build')
    self.fake_config.set(fsnbt_name, 'suite', 'fake_suite_base')
    self.fake_config.set(fsnbt_name, 'boards', 'link, zako, grunt')
    frnbt_name = 'FakeRelaxedNewBuildTask'
    self.fake_config.add_section(frnbt_name)
    self.fake_config.set(frnbt_name, 'run_on', 'new_build')
    self.fake_config.set(frnbt_name, 'suite', 'fake_suite_relaxed')
    self.fake_config.set(frnbt_name, 'only_hwtest_sanity_required', 'True')
    self.fake_config.set(frnbt_name, 'boards', 'link, zako, grunt')

    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    # Validate that the expected tests got kicked off.
    self.assertEqual(len(suite_trigger.event_results), 1)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    # 2 for strict passed builds, 3 for relaxed builds.
    self.assertEqual(len(tasks), 5)

    # The number of builds that matched the base (success) Task.
    count_base = 0
    # The number of builds that matched the relaxed Task.
    count_relaxed = 0
    for task in tasks:
      if 'fake_suite_base' in task.payload:
        # Make sure it matched the expected build only.
        self.assertNotIn('grunt-release', task.payload)
        count_base += 1

      if 'fake_suite_relaxed' in task.payload:
        count_relaxed += 1

    # Make each case matched precisely one event.
    self.assertEqual(2, count_base)
    self.assertEqual(3, count_relaxed)

  def testNewBuildWithExistingBoardFamilies(self):
    """Test the new_build suite with an existing board family."""
    link_suite = 'FakeLinkNewBuildTask'
    self.fake_config.add_section(link_suite)
    self.fake_config.set(link_suite, 'run_on', 'new_build')
    self.fake_config.set(link_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(link_suite, 'board_families', 'ivybridge')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [link_suite])
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)
    self.assertIn('link-release', tasks[0].payload)

  def testNewBuildWithExistingBoardFamiliesAndBoards(self):
    """Test the new_build suite with an existing board family."""
    link_suite = 'FakeLinkNewBuildTask'
    self.fake_config.add_section(link_suite)
    self.fake_config.set(link_suite, 'run_on', 'new_build')
    self.fake_config.set(link_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(link_suite, 'board_families', 'ivybridge')
    self.fake_config.set(link_suite, 'boards', 'asuka, paine, banon')
    self._mock_config_reader.return_value = self.fake_config

    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [link_suite])
    boards = suite_trigger.events['new_build'].task_list[0].boards
    self.assertIn('asuka', boards)
    self.assertIn('link', boards)

  def testNewBuildWithNonExistingBoardFamilies(self):
    """Test the new_build suite with an non-existing board family."""
    nyan_suite = 'FakeNonExistBoardFamiliesNewBuildTask'
    self.fake_config.add_section(nyan_suite)
    self.fake_config.set(nyan_suite, 'run_on', 'new_build')
    self.fake_config.set(nyan_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(nyan_suite, 'board_families', 'nyan')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 0)

  def testNewBuildWithNonSpecifiedBoardFamily(self):
    """Test the new_build suite with an non-specified board family."""
    normal_suite = 'FakeBoardFamiliesNewBuildTask'
    self.fake_config.add_section(normal_suite)
    self.fake_config.set(normal_suite, 'run_on', 'new_build')
    self.fake_config.set(normal_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(normal_suite, 'boards', 'link, zako')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [normal_suite])
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 2)

  def testNewBuildExcludingExistingBoardFamilies(self):
    """Test the new_build suite excluding an existing board family."""
    link_suite = 'FakeLinkNewBuildTask'
    self.fake_config.add_section(link_suite)
    self.fake_config.set(link_suite, 'run_on', 'new_build')
    self.fake_config.set(link_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(link_suite, 'exclude_board_families', 'ivybridge')
    self.fake_config.set(link_suite, 'boards', 'link, zako')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [link_suite])
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)
    self.assertNotIn('link-release', tasks[0].payload)
    self.assertIn('zako-release', tasks[0].payload)

  def testNewBuildExcludingExistingBoardFamiliesAndBoards(self):
    """Test the new_build suite with an existing board family."""
    link_suite = 'FakeLinkNewBuildTask'
    self.fake_config.add_section(link_suite)
    self.fake_config.set(link_suite, 'run_on', 'new_build')
    self.fake_config.set(link_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(link_suite, 'exclude_board_families', 'ivybridge')
    self.fake_config.set(link_suite, 'exclude_boards',
        'asuka, paine, banon, coral, reef, nami, samus-kernelnext')
    self._mock_config_reader.return_value = self.fake_config

    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [link_suite])
    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)
    self.assertNotIn('link-release', tasks[0].payload)
    self.assertNotIn('asuka-release', tasks[0].payload)
    self.assertIn('zako-release', tasks[0].payload)

  def testNewBuildExcludingNonExistingBoardFamilies(self):
    """Test the new_build suite excluding an non-existing board family."""
    nyan_suite = 'FakeNonExistExcludeBoardFamiliesNewBuildTask'
    self.fake_config.add_section(nyan_suite)
    self.fake_config.set(nyan_suite, 'run_on', 'new_build')
    self.fake_config.set(nyan_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(nyan_suite, 'exclude_board_families', 'nyan')
    self.fake_config.set(nyan_suite, 'boards', 'link, zako')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 2)

  def testNewBuildWithBoardExcludeBoardCollision(self):
    """Test the case that the same board in boards and exclude_boards."""
    normal_suite = 'FakeBoardExludingBoardCollisionNewBuildTask'
    self.fake_config.add_section(normal_suite)
    self.fake_config.set(normal_suite, 'run_on', 'new_build')
    self.fake_config.set(normal_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(normal_suite, 'boards', 'zako, asuka')
    self.fake_config.set(normal_suite, 'exclude_boards', 'asuka')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [normal_suite])
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)
    self.assertNotIn('asuka-release', tasks[0].payload)
    self.assertIn('zako-release', tasks[0].payload)

  def testNewBuildWithKernelnext(self):
    """Test the case that suites run with board-kernelnext build."""
    normal_suite = 'FakeKernelnextSuite'
    self.fake_config.add_section(normal_suite)
    self.fake_config.set(normal_suite, 'run_on', 'new_build')
    self.fake_config.set(normal_suite, 'suite', 'fake-suite')
    self.fake_config.set(normal_suite, 'pool', 'suites')
    self.fake_config.set(normal_suite, 'boards', 'samus-kernelnext')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [normal_suite])
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)
    # Board should be 'samus'.
    self.assertIn('&board=samus&', tasks[0].payload)
    # Build should be 'samus-kernelnext-release***'.
    self.assertIn('cros_version=samus-kernelnext-release', tasks[0].payload)

  def testNewBuildWithModels(self):
    """Test the new_build suite with an existing models entry."""
    normal_suite = 'FakeModelsNewBuildTask'
    self.fake_config.add_section(normal_suite)
    self.fake_config.set(normal_suite, 'run_on', 'new_build')
    self.fake_config.set(normal_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(normal_suite, 'models', 'coral_lava, coral_santa')
    self.fake_config.set(normal_suite, 'boards', 'coral')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [normal_suite])
    self.assertIn('new_build', suite_trigger.event_results)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)
    self.assertNotIn('model=astronaut', tasks[0].payload)
    self.assertIn('model=santa', tasks[0].payload)

  def testNewBuildWithModelsForHWTestSanityRequired(self):
    """Test the new_build suite with an existing models entry."""
    normal_suite = 'FakeModelsNewBuildTask'
    self.fake_config.add_section(normal_suite)
    self.fake_config.set(normal_suite, 'run_on', 'new_build')
    self.fake_config.set(normal_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(normal_suite, 'models', 'nami_akali, nami_bard')
    self.fake_config.set(normal_suite, 'boards', 'nami')
    self.fake_config.set(normal_suite, 'only_hwtest_sanity_required', 'True')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [normal_suite])
    self.assertIn('new_build', suite_trigger.event_results)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 2)
    self.assertIn('model=akali', tasks[0].payload)
    self.assertIn('9868.0.0', tasks[0].payload)
    self.assertIn('model=bard', tasks[1].payload)
    self.assertIn('9867.0.0', tasks[1].payload)

  def testNewBuildWithExcludeModels(self):
    """Test the new_build suite with an existing exclude_models entry."""
    normal_suite = 'FakeExludingModelsNewBuildTask'
    self.fake_config.add_section(normal_suite)
    self.fake_config.set(normal_suite, 'run_on', 'new_build')
    self.fake_config.set(normal_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(normal_suite, 'exclude_models',
                         'coral_lava, coral_santa')
    self.fake_config.set(normal_suite, 'boards', 'coral')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [normal_suite])
    self.assertIn('new_build', suite_trigger.event_results)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)
    self.assertNotIn('model=santa', tasks[0].payload)
    self.assertIn('model=astronaut', tasks[0].payload)

  def testNewBuildWithModelsExcludeModels(self):
    """Test the new_build suite with models and exclude_models entry."""
    normal_suite = 'FakeModelsExcludeModelsNewBuildTask'
    self.fake_config.add_section(normal_suite)
    self.fake_config.set(normal_suite, 'run_on', 'new_build')
    self.fake_config.set(normal_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(normal_suite, 'models', 'coral_santa, coral_astronaut')
    self.fake_config.set(normal_suite, 'exclude_models',
                         'coral_lava, coral_santa')
    self.fake_config.set(normal_suite, 'boards', 'coral')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertEqual(len(suite_trigger.event_results), 1)
    self.assertEqual(suite_trigger.event_results['new_build'],
                     [normal_suite])
    self.assertIn('new_build', suite_trigger.event_results)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)
    self.assertNotIn('model=santa', tasks[0].payload)
    self.assertIn('model=astronaut', tasks[0].payload)

  def testNewBuildWithNoModelListAndModelBuild(self):
    """Test the new_build suite with models and empty board_model mapping."""
    normal_suite = 'FakeModelsExcludeModelsNewBuildTask'
    self.fake_config.add_section(normal_suite)
    self.fake_config.set(normal_suite, 'run_on', 'new_build')
    self.fake_config.set(normal_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(normal_suite, 'boards', 'coral')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertIn('new_build', suite_trigger.event_results)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    # Verify that coral-release is not kicked off on model lava as lava is not
    # listed in cros_model_map.
    self.assertEqual(len(tasks), 2)
    self.assertNotIn('lava', tasks[0].payload)
    self.assertNotIn('lava', tasks[1].payload)

  def testNewBuildWithNoModelListAndNoModelBuild(self):
    """Test the new_build suite with models and empty board_model mapping."""
    normal_suite = 'FakeModelsExcludeModelsNewBuildTask'
    self.fake_config.add_section(normal_suite)
    self.fake_config.set(normal_suite, 'run_on', 'new_build')
    self.fake_config.set(normal_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(normal_suite, 'boards', 'reef')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    self.assertIn('new_build', suite_trigger.event_results)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    # Verify that reef-release is kicked off on reef models.
    self.assertEqual(len(tasks), 1)
    self.assertIn('model=electro', tasks[0].payload)

  def testNewBuildWithAnyModel(self):
    """Test the new_build suite with any_model option set."""
    normal_suite = 'FakeAnyModelNewBuildTask'
    self.fake_config.add_section(normal_suite)
    self.fake_config.set(normal_suite, 'run_on', 'new_build')
    self.fake_config.set(normal_suite, 'suite', 'fake_suite_base')
    self.fake_config.set(normal_suite, 'any_model', 'True')
    self.fake_config.set(normal_suite, 'boards', 'coral')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)
    self.assertIn('model=None', tasks[0].payload)

  def testNewBuildWithFirmwareTask(self):
    """Test the new_build suite with firmware option set."""
    # Construct a fake config with firmware build.
    fsnbt_name = 'FakeStrictNewBuildTask'
    self.fake_config.add_section(fsnbt_name)
    self.fake_config.set(fsnbt_name, 'run_on', 'new_build')
    self.fake_config.set(fsnbt_name, 'suite', 'fake_suite_base')
    self.fake_config.set(fsnbt_name, 'boards', 'zako')
    self.fake_config.set(fsnbt_name, 'firmware_ro_build_spec', 'firmware')
    self.fake_config.set(fsnbt_name, 'test_source', 'cros')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    some_event = suite_trigger.events['new_build']
    suite_trigger.cron()

    # The firmware query has run for once.
    self.assertEqual(suite_trigger._build_client.firmware_builds_called, 1)
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)
    self.assertIn('firmware-zako-12345.67', tasks[0].payload)


  def testNewBuildWithoutFirmwareTask(self):
    """Test the event skips fetch the firmware builds."""
    # Construct a fake config without firmware build.
    fsnbt_name = 'FakeStrictNewBuildTask'
    self.fake_config.add_section(fsnbt_name)
    self.fake_config.set(fsnbt_name, 'run_on', 'new_build')
    self.fake_config.set(fsnbt_name, 'suite', 'fake_suite_base')
    self.fake_config.set(fsnbt_name, 'boards', 'zako')
    self._mock_config_reader.return_value = self.fake_config

    queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    # The firmware query was not called.
    self.assertEqual(suite_trigger._build_client.firmware_builds_called, 0)
    # Validate that the expected tests got kicked off.
    tasks = queue.lease_tasks(3600, 10, deadline=0.5)
    self.assertEqual(len(tasks), 1)


class TriggerReceiverRealConfigTestCase(TriggerReceiverBaseTestCase):

  def setUp(self):
    super(TriggerReceiverRealConfigTestCase, self).setUp()
    mock_config_reader = mock.patch('config_reader.ConfigReader')
    self._mock_config_reader = mock_config_reader.start()
    self.addCleanup(mock_config_reader.stop)
    self._mock_config_reader.return_value = _SUITE_CONFIG_READER

  def _get_ground_truth_task_list_from_config(self):
    """Get the ground truth of to-be-scheduled task list from config file."""
    self._mock_utc_now.return_value = datetime.datetime.now(
        time_converter.UTC_TZ)
    task_config = task_config_reader.TaskConfig(_SUITE_CONFIG_READER)
    tasks = {}
    for keyword, klass in task_config_reader.EVENT_CLASSES.iteritems():
      new_event = klass(
          task_config.get_event_setting(klass.section_name()), None)
      new_event.set_task_list(
          task_config.get_tasks_by_keyword(klass.KEYWORD)['tasks'])
      tasks[keyword] = new_event.task_list

    return tasks

  def testCronWithoutLastExec(self):
    """Test the first round of cron can be successfully executed."""
    self._mock_utc_now.return_value = datetime.datetime.now(
        time_converter.UTC_TZ)
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()
    self.assertFalse(suite_trigger.events['nightly'].should_handle)
    self.assertFalse(suite_trigger.events['weekly'].should_handle)
    self.assertFalse(suite_trigger.events['new_build'].should_handle)

    self.assertEqual(suite_trigger.event_results, {})

  def testCronTriggerNightly(self):
    """Test nightly event is read with available nightly last_exec_time."""
    utc_now = datetime.datetime.now(time_converter.UTC_TZ)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        'nightly', utc_now - datetime.timedelta(hours=1))
    self._mock_utc_now.return_value = utc_now
    suite_trigger = trigger_receiver.TriggerReceiver()
    self.assertTrue(suite_trigger.events['nightly'].should_handle)
    self.assertFalse(suite_trigger.events['weekly'].should_handle)
    self.assertFalse(suite_trigger.events['new_build'].should_handle)

  def testCronTriggerNightlyOutdated(self):
    """Test nightly event is read with available nightly last_exec_time."""
    utc_now = datetime.datetime.now(time_converter.UTC_TZ)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        'nightly', utc_now - datetime.timedelta(days=3))
    self._mock_utc_now.return_value = utc_now
    suite_trigger = trigger_receiver.TriggerReceiver()
    self.assertFalse(suite_trigger.events['nightly'].should_handle)

  def testCronTriggerWeeklyOutdated(self):
    """Test weekly event is read with available weekly last_exec_time."""
    utc_now = datetime.datetime.now(time_converter.UTC_TZ)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        'weekly', utc_now - datetime.timedelta(days=8))
    self._mock_utc_now.return_value = utc_now
    suite_trigger = trigger_receiver.TriggerReceiver()
    self.assertFalse(suite_trigger.events['weekly'].should_handle)

  def testCronForWeeks(self):
    """Ensure cron job can be successfully scheduled for several weeks."""
    all_tasks = self._get_ground_truth_task_list_from_config()
    last_now = None

    for now in now_generator(datetime.datetime.now(time_converter.UTC_TZ)):
      self._mock_utc_now.return_value = now
      suite_trigger = trigger_receiver.TriggerReceiver()
      with mock.patch('task.Task.schedule', return_value=True):
        suite_trigger.cron()

      should_scheduled_nightly_tasks = [
          t.name for t in all_tasks['nightly'] if t.hour == now.hour]

      if (_should_schedule_timed_task(last_now, now) and
          should_scheduled_nightly_tasks):
        self.assertEqual(suite_trigger.event_results['nightly'],
                         should_scheduled_nightly_tasks)
      else:
        self.assertNotIn('nightly', suite_trigger.event_results.keys())

      # Verify weekly tasks
      should_scheduled_weekly_tasks = [
          t.name for t in all_tasks['weekly']
          if now.weekday() == t.day and now.hour == t.hour]
      if (_should_schedule_timed_task(last_now, now) and
          should_scheduled_weekly_tasks):
        self.assertEqual(suite_trigger.event_results['weekly'],
                         should_scheduled_weekly_tasks)
      else:
        self.assertNotIn('weekly', suite_trigger.event_results.keys())

      # Verify new_build tasks
      should_scheduled_new_build_tasks = [
          t.name for t in all_tasks['new_build']]
      if (_should_schedule_new_build_task(last_now, now) and
          should_scheduled_new_build_tasks):
        self.assertEqual(suite_trigger.event_results['new_build'],
                         should_scheduled_new_build_tasks)
      else:
        self.assertNotIn('new_build', suite_trigger.event_results.keys())

      last_now = now


if __name__ == '__main__':
  unittest.main()
