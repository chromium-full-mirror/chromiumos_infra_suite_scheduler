# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for trigger_receiver unittests."""

import datetime
import os
import unittest

import cloud_sql_client
import config_reader
import datastore_client
import file_getter
import mock
import time_converter
import trigger_receiver

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


def _should_schedule_nightly_task(last_now, now):
  """Check whether nightly task should be scheduled.

  A nightly task should be schduled when next hour is coming.

  Args:
    last_now: the last time to check if nightly task should be scheduled
      or not.
    now: the current time to check if nightly task should be scheduled.

  Returns:
    a boolean indicating whether there will be nightly tasks scheduled.
  """
  if last_now is not None and last_now.hour != now.hour:
    return True

  return False


def _should_schedule_weekly_task(last_now, now, weekly_time_info):
  """Check whether weekly task should be scheduled.

  A weekly task should be schduled when it comes to the default weekly tasks
  scheduling hour in next day.

  Args:
    last_now: the last time to check if weekly task should be scheduled
      or not.
    now: the current time to check if weekly task should be scheduled.
    weekly_time_info: the default weekly tasks scheduling time info.

  Returns:
    a boolean indicating whether there will be weekly tasks scheduled.
  """
  if (last_now is not None and last_now.hour != now.hour and
      now.hour == weekly_time_info.hour):
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


class FakeCIDBClient(object):
  """Mock cloud_sql_client.CIDBClient."""

  def get_passed_builds_since_date(self, since_date):
    """Mock cloud_sql_client.CIDBClient.get_passed_builds_since_date."""
    del since_date  # unused
    return [cloud_sql_client.BuildInfo('link', '62', '9868.0.0',
                                       'link-release')]

  def get_latest_passed_builds(self, build_config):
    """Mock cloud_sql_client.CIDBClient.get_latest_passed_builds."""
    del build_config  # unused
    return cloud_sql_client.BuildInfo('link', '62', '9868.0.0', build_config)


class FakeAndroidBuildRestClient(object):
  """Mock rest_client.AndroidBuildRestClient."""

  def get_latest_build_id(self, branch, target):
    """Mock rest_client.AndroidBuildRestClient.get_latest_build_id."""
    del branch, target  # unused
    return '100'


class FakeLabConfig(object):
  """Mock rest_client.AndroidBuildRestClient."""

  def get_android_board_list(self):
    """Mock config_reader.LabConfig.get_android_board_list."""
    return ('android-angler', 'android-bullhead')

  def get_cros_board_list(self):
    """Mock config_reader.LabConfig.get_android_board_list."""
    return ('link', 'peppy', 'daisy')

  def get_firmware_ro_build_list(self, release_board):
    """Mock config_reader.LabConfig.get_firmware_ro_build_list."""
    del release_board  # unused
    return 'firmware1,firmware2'

  def get_cros_model_map(self):
    """Mock config_reader.LabConfig.get_cros_model_map."""
    return {}


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

    mock_cidb_client = mock.patch('cloud_sql_client.CIDBClient')
    self._mock_cidb_client = mock_cidb_client.start()
    self.addCleanup(mock_cidb_client.stop)

    mock_android_client = mock.patch('rest_client.AndroidBuildRestClient')
    self._mock_android_client = mock_android_client.start()
    self.addCleanup(mock_android_client.stop)

    mock_lab_config = mock.patch('config_reader.LabConfig')
    self._mock_lab_config = mock_lab_config.start()
    self.addCleanup(mock_lab_config.stop)

    mock_utc_now = mock.patch('time_converter.utc_now')
    self._mock_utc_now = mock_utc_now.start()
    self.addCleanup(mock_utc_now.stop)

    self._mock_cidb_client.return_value = FakeCIDBClient()
    self._mock_android_client.return_value = FakeAndroidBuildRestClient()
    self._mock_lab_config.return_value = FakeLabConfig()


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
    weekly_section_name = config_reader.EVENT_CLASSES['weekly'].section_name()
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
            config_reader.EVENT_CLASSES['weekly'].DEFAULT_PST_HOUR)).hour
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
    task_config = config_reader.TaskConfig(_SUITE_CONFIG_READER)
    tasks = {}
    for keyword, klass in config_reader.EVENT_CLASSES.iteritems():
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
    nightly_time_info = time_converter.convert_time_info(
        time_converter.TimeInfo(
            config_reader.EVENT_CLASSES['nightly'].DEFAULT_PST_DAY,
            config_reader.EVENT_CLASSES['nightly'].DEFAULT_PST_HOUR))
    weekly_time_info = time_converter.convert_time_info(
        time_converter.TimeInfo(
            config_reader.EVENT_CLASSES['weekly'].DEFAULT_PST_DAY,
            config_reader.EVENT_CLASSES['weekly'].DEFAULT_PST_HOUR))
    last_now = None

    for now in now_generator(datetime.datetime.now(time_converter.UTC_TZ)):
      self._mock_utc_now.return_value = now
      suite_trigger = trigger_receiver.TriggerReceiver()
      with mock.patch('task.Task.schedule', return_value=True):
        suite_trigger.cron()

      should_scheduled_nightly_tasks = [
          t.name for t in all_tasks['nightly']
          if (t.hour is not None and t.hour == now.hour) or
          (t.hour is None and now.hour == nightly_time_info.hour)]

      if (_should_schedule_nightly_task(last_now, now) and
          should_scheduled_nightly_tasks):
        self.assertEqual(suite_trigger.event_results['nightly'],
                         should_scheduled_nightly_tasks)
      else:
        self.assertNotIn('nightly', suite_trigger.event_results.keys())

      # Verify weekly tasks
      should_scheduled_weekly_tasks = [
          t.name for t in all_tasks['weekly']
          if (t.day is not None and now.weekday() == t.day) or
          (t.day is None and now.weekday() == weekly_time_info.weekday)]
      if (_should_schedule_weekly_task(last_now, now, weekly_time_info) and
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
