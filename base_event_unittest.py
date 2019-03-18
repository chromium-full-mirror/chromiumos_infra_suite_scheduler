# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for timed_event unittests."""

import datetime
import unittest

import base_event
import config_reader
import datastore_client
import mock
import task
import task_config_reader
import time_converter

from google.appengine.ext import ndb
from google.appengine.ext import testbed


# pylint: disable=unused-argument
class FakeTask(object):

  def __init__(self, name, success, lc_branches='', lc_targets=''):
    self.name = name
    self.success = success
    self.launch_control_branches = lc_branches.split(',')
    self.launch_control_targets = lc_targets.split(',')

  def schedule(self, lc_builds, cros_builds, lab_config, db_client=None):
    if not self.success:
      raise task.SchedulingError('Failed to run task.')

    return self.success
# pylint: enable=unused-argument


class BaseEventTestCase(unittest.TestCase):

  _KLASS = base_event.BaseEvent

  def setUp(self):
    super(BaseEventTestCase, self).setUp()
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

  def testCreateEventWithAlwaysHandle(self):
    """Create a base event with always_handle=True."""
    utc_now = datetime.datetime(2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    event = self._KLASS(
        task_config_reader.EventSettings(True, None), utc_now, utc_now)

    self.assertEqual(event.target_exec_utc, utc_now)
    self.assertEqual(event.last_exec_utc, utc_now)
    self.assertTrue(event.always_handle)
    self.assertTrue(event.should_handle)

  def testCreateEventWithoutAlwaysHandle(self):
    """Create a base event with always_handle=False."""
    utc_now = datetime.datetime(2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    event = self._KLASS(
        task_config_reader.EventSettings(False, None), utc_now, utc_now)

    self.assertEqual(event.target_exec_utc, utc_now)
    self.assertEqual(event.last_exec_utc, utc_now)
    self.assertFalse(event.always_handle)
    self.assertFalse(event.should_handle)

  def testProcessTasks(self):
    """Test process_tasks() for event."""
    utc_now = datetime.datetime(2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    event = self._KLASS(
        task_config_reader.EventSettings(True, None), utc_now, utc_now)
    task_list = [FakeTask('test1', True), FakeTask('test2', False)]
    event.set_task_list(task_list)
    finished_tasks = event.process_tasks(None, None, None, None)
    self.assertEqual(len(finished_tasks), 1)
    self.assertEqual(finished_tasks[0], 'test1')

  def testEventFinish(self):
    """Test finish() for event."""
    utc_now = datetime.datetime(2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    last_exec_utc = utc_now - datetime.timedelta(hours=1)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(self._KLASS.KEYWORD, last_exec_utc)
    event = self._KLASS(
        task_config_reader.EventSettings(True, None), last_exec_utc, utc_now)

    self.assertEqual(
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD),
        last_exec_utc)

    event.finish()
    self.assertEqual(
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD),
        utc_now)

  def testPropertyLaunchControlBranchTargets(self):
    """Test getter of property launch_control_branch_targets."""
    utc_now = datetime.datetime(2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    event = self._KLASS(
        task_config_reader.EventSettings(True, None), utc_now, utc_now)
    task_list = [FakeTask('test1', True, 'b1', 't1,t2'),
                 FakeTask('test2', True, 'b2', 't3,t4'),
                 FakeTask('test3', True, 'b1', 't5,t6')]
    event.set_task_list(task_list)
    self.assertEqual(event.launch_control_branch_targets,
                     {'b1': ['t1', 't2', 't5', 't6'],
                      'b2': ['t3', 't4']})

  def testGAETestingForShouldHandle(self):
    """Verify that testing on GAE staging will cause event to handle."""
    utc_now = datetime.datetime(2017, 8, 1, 4, tzinfo=time_converter.UTC_TZ)
    with mock.patch('global_config.GAE_TESTING', return_value=True):
      event = self._KLASS(
          task_config_reader.EventSettings(True, None), utc_now, utc_now)
      self.assertTrue(event.should_handle)
