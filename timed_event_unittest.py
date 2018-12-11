# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for timed_event unittests."""
# pylint: disable=g-missing-super-call

import datetime
import unittest

import config_reader
import datastore_client
import mock
import time_converter
import timed_event

from google.appengine.ext import ndb
from google.appengine.ext import testbed


class FakeTask(object):

  def __init__(self, name, day=None, hour=None):
    self.name = name
    self.day = day
    self.hour = hour


class TimedEventTestCase(unittest.TestCase):

  def setUp(self):
    mock_utc_now = mock.patch('time_converter.utc_now')
    self._mock_utc_now = mock_utc_now.start()
    self.addCleanup(mock_utc_now.stop)

    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.addCleanup(self.testbed.deactivate)
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_memcache_stub()
    ndb.get_context().clear_cache()

    self.config = config_reader.ConfigReader(None)


class NightlyEventTestCase(TimedEventTestCase):

  _KLASS = timed_event.Nightly
  _DEFAULT_PST_HOUR = _KLASS.DEFAULT_PST_HOUR
  _DEFAULT_UTC_HOUR = time_converter.convert_time_info(
      time_converter.TimeInfo(None, _DEFAULT_PST_HOUR)).hour

  def testCreateNightlyEventWithoutLastExec(self):
    """Create a nightly event without last_exec_utc in datastore."""
    utc_now = datetime.datetime(2017, 8, 1, 4, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(2017, 8, 1, 4,
                                               tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))

    self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
    self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
    self.assertFalse(event.should_handle)

  def testCreateNightlyEventWithValidLastExecShouldNotHandle(self):
    """Create a nightly event with last_exec_utc but shouldn't be handled."""
    utc_now = datetime.datetime(2017, 8, 1, 4, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(2017, 8, 1, 4,
                                               tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD, expected_last_exec_utc)
    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))

    self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
    self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
    self.assertFalse(event.should_handle)

  def testCreateCantHandleNightlyEventWithValidLastExecWithGAETesting(self):
    """Test a can't-be-handled event can be handled in testing on GAE."""
    utc_now = datetime.datetime(2017, 8, 1, 4, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(2017, 8, 1, 4,
                                               tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD, expected_last_exec_utc)

    with mock.patch('global_config.GAE_TESTING', return_value=True):
      event = self._KLASS(
          task_config.get_event_setting(self._KLASS.section_name()),
          last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
      self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
      self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
      self.assertTrue(event.should_handle)

  def testCreateNightlyEventWithValidLastExecShouldHandle(self):
    """Create a nightly event with last_exec_utc and should be handled."""
    utc_now = datetime.datetime(2017, 8, 1, 5, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(2017, 8, 1, 4,
                                               tzinfo=time_converter.UTC_TZ)
    expected_cur_exec_utc = datetime.datetime(2017, 8, 1, 5,
                                              tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD, expected_last_exec_utc)
    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))

    self.assertEqual(event.target_exec_utc, expected_cur_exec_utc)
    self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
    self.assertTrue(event.should_handle)

  def testCreateNightlyEventWithOutdatedLastExec(self):
    """Create a nightly event with outdated last_exec_utc."""
    utc_now = datetime.datetime(2017, 8, 1, 4, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(2017, 8, 1, 4,
                                               tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD,
        expected_last_exec_utc - datetime.timedelta(hours=3))
    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))

    self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
    self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
    self.assertFalse(event.should_handle)

  def testCreateNightlyEventWithOutdatedLastExecWithGAETesting(self):
    """Test an event with old last exec can be handled in testing on GAE."""
    utc_now = datetime.datetime(2017, 8, 1, 4, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(2017, 8, 1, 4,
                                               tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD,
        expected_last_exec_utc - datetime.timedelta(hours=3))

    with mock.patch('global_config.GAE_TESTING', return_value=True):
      event = self._KLASS(
          task_config.get_event_setting(self._KLASS.section_name()),
          last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
      self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
      self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
      self.assertTrue(event.should_handle)

  def testFilterTasksWithTaskHourForNightlyEvent(self):
    """Test filter_tasks with tasks which contain settings of hour."""
    default_pst_hour = time_converter.convert_time_info(
        time_converter.TimeInfo(None, 0),
        source_tz=time_converter.UTC_TZ,
        target_tz=time_converter.PST_TZ).hour
    utc_now = datetime.datetime(2017, 8, 1, 0, 15,
                                tzinfo=time_converter.UTC_TZ)
    self._mock_utc_now.return_value = utc_now
    event = self._KLASS(
        config_reader.EventSettings(True, None),
        datetime.datetime(2017, 7, 31, 23, tzinfo=time_converter.UTC_TZ))

    # It's in PST time.
    task_list = [FakeTask('test1', day=None, hour=default_pst_hour+1),
                 FakeTask('test2', day=None, hour=default_pst_hour),
                 FakeTask('test3', day=None, hour=0),
                 FakeTask('test4', day=None, hour=default_pst_hour)]
    event.set_task_list(task_list)
    self.assertEqual(len(event.task_list), len(task_list))
    event.filter_tasks()
    # Verify only tasks that should be run at 0:00 in UTC are kept,
    # since current time is 0:15.
    self.assertEqual(len(event.task_list), 2)
    self.assertEqual(sorted([t.name for t in event.task_list]),
                     ['test2', 'test4'])

  def testFilterTasksWithDefaultHourForNightlyEvent(self):
    """Test filter_tasks with tasks which don't contain settings of hour."""
    utc_now = datetime.datetime(2017, 8, 1, self._DEFAULT_UTC_HOUR, 15,
                                tzinfo=time_converter.UTC_TZ)
    self._mock_utc_now.return_value = utc_now
    event = self._KLASS(
        config_reader.EventSettings(True, None),
        datetime.datetime(2017, 8, 1, 3, tzinfo=time_converter.UTC_TZ))

    # It's in PST time.
    task_list = [FakeTask('test1', day=None, hour=self._DEFAULT_PST_HOUR - 1),
                 FakeTask('test2', day=None, hour=self._DEFAULT_PST_HOUR),
                 FakeTask('test3', day=None, hour=self._DEFAULT_PST_HOUR + 1),
                 FakeTask('test4', day=None, hour=None)]
    event.set_task_list(task_list)
    self.assertEqual(len(event.task_list), len(task_list))
    event.filter_tasks()
    # Verify only tasks that should be run at 21:00 (the default pst hour
    # for nightly events) are kept.
    self.assertEqual(len(event.task_list), 2)
    self.assertEqual(sorted([t.name for t in event.task_list]),
                     ['test2', 'test4'])

  def testFilterTasksWithTaskHourWithGAETesting(self):
    """Verify all tasks are kept when testing on GAE."""
    utc_now = datetime.datetime(2017, 8, 1, 0, 15,
                                tzinfo=time_converter.UTC_TZ)
    self._mock_utc_now.return_value = utc_now

    with mock.patch('global_config.GAE_TESTING', return_value=True):
      event = self._KLASS(
          config_reader.EventSettings(True, None),
          datetime.datetime(2017, 7, 31, 23, tzinfo=time_converter.UTC_TZ))

      task_list = [FakeTask('test1', day=None, hour=3),
                   FakeTask('test2', day=None, hour=0),
                   FakeTask('test3', day=None, hour=4),
                   FakeTask('test4', day=None, hour=0)]
      event.set_task_list(task_list)
      self.assertEqual(len(event.task_list), len(task_list))
      event.filter_tasks()
      self.assertEqual(len(event.task_list), 4)
      self.assertEqual(sorted([t.name for t in event.task_list]),
                       ['test1', 'test2', 'test3', 'test4'])

  def testSetTaskListForNightlyEvent(self):
    """Verify tasks' timeinfo are correctly converted to UTC."""
    self._mock_utc_now.return_value = datetime.datetime.now(
        time_converter.UTC_TZ)
    event = self._KLASS(
        config_reader.EventSettings(True, None), None)

    # It's in PST time.
    task_list = [FakeTask('test1', day=None, hour=self._DEFAULT_PST_HOUR),
                 FakeTask('test2', day=None, hour=0),
                 FakeTask('test3', day=None, hour=self._DEFAULT_PST_HOUR+1),
                 FakeTask('test4', day=None, hour=None)]
    event.set_task_list(task_list)
    tasks_with_default_utc_hour = [
        t.name for t in event.task_list if t.hour == self._DEFAULT_UTC_HOUR]
    self.assertEqual(sorted(tasks_with_default_utc_hour),
                     ['test1', 'test4'])


class WeeklyEventTestCase(TimedEventTestCase):

  _KLASS = timed_event.Weekly
  _DEFAULT_PST_DAY = _KLASS.DEFAULT_PST_DAY
  _DEFAULT_PST_HOUR = _KLASS.DEFAULT_PST_HOUR
  _DEFAULT_UTC_TIMEINFO = time_converter.convert_time_info(
      time_converter.TimeInfo(_DEFAULT_PST_DAY, _DEFAULT_PST_HOUR))
  _DEFAULT_UTC_DAY = _DEFAULT_UTC_TIMEINFO.weekday
  _DEFAULT_UTC_HOUR = _DEFAULT_UTC_TIMEINFO.hour

  def testCreateWeeklyEventWithoutLastExec(self):
    """Create a weekly event without last_exec_utc in datastore."""
    utc_now = datetime.datetime(2017, 8, 1, 4, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(
        2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))

    self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
    self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
    self.assertFalse(event.should_handle)

  def testCreateWeeklyEventWithoutLastExecWithGAETesting(self):
    """Test an event without last exec can be handled in testing on GAE."""
    utc_now = datetime.datetime(2017, 8, 1, 4, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(
        2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()

    with mock.patch('global_config.GAE_TESTING', return_value=True):
      event = self._KLASS(
          task_config.get_event_setting(self._KLASS.section_name()),
          last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))

      self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
      self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
      self.assertTrue(event.should_handle)

  def testCreateWeeklyEventWithValidLastExecShouldNotHandle(self):
    """Create a weekly event with last_exec_utc but shouldn't be handled."""
    utc_now = datetime.datetime(2017, 8, 1, self._DEFAULT_UTC_HOUR-1, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(
        2017, 8, 1, self._DEFAULT_UTC_HOUR-1, tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD, expected_last_exec_utc)

    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
    self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
    self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
    self.assertFalse(event.should_handle)

  def testCreateCantHandleWeeklyEventWithValidLastExecWithGAETesting(self):
    """Test a can't-be-handled event can be handled in testing on GAE."""
    utc_now = datetime.datetime(2017, 8, 1, 4, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(
        2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD, expected_last_exec_utc)

    with mock.patch('global_config.GAE_TESTING', return_value=True):
      event = self._KLASS(
          task_config.get_event_setting(self._KLASS.section_name()),
          last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
      self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
      self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
      self.assertTrue(event.should_handle)

  def testCreateWeeklyEventWithValidLastExecShouldHandle(self):
    """Create a nightly event with last_exec_utc and should be handled."""
    utc_now = datetime.datetime(2017, 8, 1, self._DEFAULT_UTC_HOUR, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(
        2017, 7, 31, self._DEFAULT_UTC_HOUR, tzinfo=time_converter.UTC_TZ)
    expected_cur_exec_utc = datetime.datetime(
        2017, 8, 1, self._DEFAULT_UTC_HOUR, tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD, expected_last_exec_utc)

    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
    self.assertEqual(event.target_exec_utc, expected_cur_exec_utc)
    self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
    self.assertTrue(event.should_handle)

  def testCreateWeeklyEventWithOutdatedLastExec(self):
    """Create a weekly event with outdated last_exec_utc."""
    utc_now = datetime.datetime(2017, 8, 1, 4, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(
        2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD,
        expected_last_exec_utc - datetime.timedelta(days=3))

    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
    self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
    self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
    self.assertFalse(event.should_handle)

  def testCreateWeeklyEventWithOutdatedLastExecWithGAETesting(self):
    """Test an event with old last exec can be handled in testing on GAE."""
    utc_now = datetime.datetime(2017, 8, 1, 4, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(
        2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD,
        expected_last_exec_utc - datetime.timedelta(days=3))

    with mock.patch('global_config.GAE_TESTING', return_value=True):
      event = self._KLASS(
          task_config.get_event_setting(self._KLASS.section_name()),
          last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
      self.assertEqual(event.target_exec_utc, expected_last_exec_utc)
      self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
      self.assertTrue(event.should_handle)

  def testCreateWeeklyEventWithEventHourSettings(self):
    """Create a weekly event with setting event hour."""
    self.config.add_section(self._KLASS.section_name())
    # Set weekly default kick off time to everyday 14:00 PST (21:00 UTC).
    self.config.set(self._KLASS.section_name(), 'hour', '14')
    expected_utc_hour = time_converter.convert_time_info(
        time_converter.TimeInfo(self._DEFAULT_PST_DAY, 14)).hour
    utc_now = datetime.datetime(2017, 8, 1, expected_utc_hour, 15,
                                tzinfo=time_converter.UTC_TZ)
    expected_last_exec_utc = datetime.datetime(
        2017, 7, 31, expected_utc_hour, tzinfo=time_converter.UTC_TZ)
    expected_cur_exec_utc = datetime.datetime(
        2017, 8, 1, expected_utc_hour, tzinfo=time_converter.UTC_TZ)
    task_config = config_reader.TaskConfig(self.config)
    self._mock_utc_now.return_value = utc_now
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(
        self._KLASS.KEYWORD, expected_last_exec_utc)

    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
    self.assertEqual(event.target_exec_utc, expected_cur_exec_utc)
    self.assertEqual(event.last_exec_utc, expected_last_exec_utc)
    self.assertTrue(event.should_handle)

  def testFilterTasksWithTaskDayForWeeklyEvent(self):
    """Test filter_tasks with tasks which contain settings of day."""
    utc_now = datetime.datetime(2017, 8, 6, self._DEFAULT_UTC_HOUR, 15,
                                tzinfo=time_converter.UTC_TZ)
    self._mock_utc_now.return_value = utc_now
    event = self._KLASS(
        config_reader.EventSettings(True, None),
        datetime.datetime(2017, 8, 5, self._DEFAULT_UTC_HOUR,
                          tzinfo=time_converter.UTC_TZ))

    # It's in PST time.
    task_list = [FakeTask('test1', day=5),
                 FakeTask('test2', day=0),
                 FakeTask('test3', day=3),
                 FakeTask('test4', day=5)]
    event.set_task_list(task_list)
    self.assertEqual(len(event.task_list), len(task_list))
    event.filter_tasks()
    # Verify only tasks that should be run at Saturday 23:00 in PST are kept,
    # since 2017-08-06 6:00 is Sunday in UTC.
    self.assertEqual(len(event.task_list), 2)
    self.assertEqual(sorted([t.name for t in event.task_list]),
                     ['test1', 'test4'])

  def testFilterTasksWithDefaultDayForWeeklyEvent(self):
    """Test filter_tasks with tasks which don't contain settings of day."""
    utc_now = datetime.datetime(2017, 8, 6, self._DEFAULT_UTC_HOUR, 15,
                                tzinfo=time_converter.UTC_TZ)
    self._mock_utc_now.return_value = utc_now
    event = self._KLASS(
        config_reader.EventSettings(True, None),
        datetime.datetime(2017, 8, 5, self._DEFAULT_UTC_HOUR,
                          tzinfo=time_converter.UTC_TZ))

    # It's in PST time.
    task_list = [FakeTask('test1', day=5),
                 FakeTask('test2', day=6),
                 FakeTask('test3', day=4),
                 FakeTask('test4', day=None)]
    event.set_task_list(task_list)
    self.assertEqual(len(event.task_list), len(task_list))
    event.filter_tasks()
    # Verify only tasks that should be run at Saturday 23:00 in PST are kept,
    # since 2017-08-06 6:00 is Sunday in UTC.
    # If a task's day is not set, by default it should be run at
    # 6:00 at every Sunday in UTC (equals to 23:00 at every Saturday in PST).
    self.assertEqual(len(event.task_list), 2)
    self.assertEqual(sorted([t.name for t in event.task_list]),
                     ['test1', 'test4'])

  def testFilterTasksWithTaskDayWithGAETesting(self):
    """Verify all tasks are kept in testing on GAE."""
    utc_now = datetime.datetime(2017, 8, 6, self._DEFAULT_UTC_HOUR, 15,
                                tzinfo=time_converter.UTC_TZ)
    self._mock_utc_now.return_value = utc_now

    with mock.patch('global_config.GAE_TESTING', return_value=True):
      event = self._KLASS(
          config_reader.EventSettings(True, None),
          datetime.datetime(2017, 8, 5, self._DEFAULT_UTC_HOUR,
                            tzinfo=time_converter.UTC_TZ))
      task_list = [FakeTask('test1', day=6),
                   FakeTask('test2', day=0),
                   FakeTask('test3', day=3),
                   FakeTask('test4', day=6)]
      event.set_task_list(task_list)
      self.assertEqual(len(event.task_list), len(task_list))
      event.filter_tasks()
      self.assertEqual(len(event.task_list), 4)
      self.assertEqual(sorted([t.name for t in event.task_list]),
                       ['test1', 'test2', 'test3', 'test4'])

  def testSetTaskListForWeeklyEventCheckWeekday(self):
    """Verify tasks' timeinfo are correctly converted to UTC."""
    self._mock_utc_now.return_value = datetime.datetime.now(
        time_converter.UTC_TZ)
    event = self._KLASS(
        config_reader.EventSettings(True, None), None)

    # It's in PST time.
    task_list = [FakeTask('test1', day=self._DEFAULT_PST_DAY),
                 FakeTask('test2', day=0),
                 FakeTask('test3', day=self._DEFAULT_PST_DAY-1),
                 FakeTask('test4', day=None)]
    event.set_task_list(task_list)
    tasks_with_default_utc_day = [
        t.name for t in event.task_list if t.day == self._DEFAULT_UTC_DAY]
    self.assertEqual(sorted(tasks_with_default_utc_day),
                     ['test1', 'test4'])

  def testSetTaskListForWeeklyEventCheckHour(self):
    """Verify tasks' timeinfo are correctly converted to UTC."""
    self._mock_utc_now.return_value = datetime.datetime.now(
        time_converter.UTC_TZ)
    event = self._KLASS(
        config_reader.EventSettings(True, None), None)

    # It's in PST time.
    task_list = [FakeTask('test1', day=self._DEFAULT_PST_DAY),
                 FakeTask('test2', day=self._DEFAULT_PST_DAY, hour=0),
                 FakeTask('test3', day=self._DEFAULT_PST_DAY,
                          hour=self._DEFAULT_PST_HOUR)]
    event.set_task_list(task_list)
    tasks_with_default_utc_hour = [
        t.name for t in event.task_list if t.hour == self._DEFAULT_UTC_HOUR]
    self.assertEqual(sorted(tasks_with_default_utc_hour),
                     ['test1', 'test3'])
