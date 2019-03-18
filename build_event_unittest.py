# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for build_event unittests."""
# pylint: disable=g-missing-super-call

import datetime
import unittest

import build_event
import config_reader
import datastore_client
import mock
import task_config_reader
import time_converter

from google.appengine.ext import ndb
from google.appengine.ext import testbed


class BuildEventTestCase(unittest.TestCase):

  _KLASS = build_event.NewBuild

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
    self.utc_now = datetime.datetime(2017, 8, 1, 2, 15,
                                     tzinfo=time_converter.UTC_TZ)
    self._mock_utc_now.return_value = self.utc_now

  def testInitBuildEventWithoutLastExec(self):
    """Test that init a Build Event without last_exec_utc in datastore."""
    task_config = task_config_reader.TaskConfig(self.config)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
    self.assertEqual(event.target_exec_utc, self.utc_now)
    self.assertEqual(event.last_exec_utc, self.utc_now)
    self.assertEqual(event.since_date, self.utc_now)
    self.assertFalse(event.always_handle)
    self.assertFalse(event.should_handle)

  def testInitBuildEventWithoutLastExecWithGAETesting(self):
    """Test BuildEvent without last exec will be handled in testing on GAE."""
    task_config = task_config_reader.TaskConfig(self.config)
    last_exec_client = datastore_client.LastExecutionRecordStore()

    with mock.patch('global_config.GAE_TESTING', return_value=True):
      event = self._KLASS(
          task_config.get_event_setting(self._KLASS.section_name()),
          last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
      self.assertEqual(event.target_exec_utc, self.utc_now)
      self.assertEqual(event.last_exec_utc, self.utc_now)
      self.assertEqual(event.since_date, self.utc_now)
      self.assertFalse(event.always_handle)
      self.assertTrue(event.should_handle)

  def testInitBuildEventWithValidLastExec(self):
    """Test that init a Build Event with a valid last_exec_utc in datastore."""
    task_config = task_config_reader.TaskConfig(self.config)
    last_exec_utc = self.utc_now - datetime.timedelta(
        hours=self._KLASS.LAST_EXEC_INTERVAL-1)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(self._KLASS.KEYWORD, last_exec_utc)
    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
    self.assertEqual(event.target_exec_utc, self.utc_now)
    self.assertEqual(event.last_exec_utc, last_exec_utc)
    self.assertEqual(event.since_date, last_exec_utc)
    self.assertFalse(event.always_handle)
    self.assertTrue(event.should_handle)

  def testInitBuildEventWithOutdatedLastExec(self):
    """Test that init a BuildEvent with a non-valid last_exec_utc."""
    task_config = task_config_reader.TaskConfig(self.config)
    last_exec_utc = self.utc_now - datetime.timedelta(
        hours=self._KLASS.LAST_EXEC_INTERVAL+1)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(self._KLASS.KEYWORD, last_exec_utc)
    event = self._KLASS(
        task_config.get_event_setting(self._KLASS.section_name()),
        last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
    self.assertEqual(event.target_exec_utc, self.utc_now)
    self.assertEqual(event.last_exec_utc, self.utc_now)
    self.assertEqual(event.since_date, self.utc_now)
    self.assertFalse(event.always_handle)
    self.assertFalse(event.should_handle)

  def testInitBuildEventWithOutdatedLastExecWithGAETesting(self):
    """Test BuildEvent with old last exec will be handled in testing on GAE."""
    task_config = task_config_reader.TaskConfig(self.config)
    last_exec_utc = self.utc_now - datetime.timedelta(
        hours=self._KLASS.LAST_EXEC_INTERVAL+1)
    last_exec_client = datastore_client.LastExecutionRecordStore()
    last_exec_client.set_last_execute_time(self._KLASS.KEYWORD, last_exec_utc)

    with mock.patch('global_config.GAE_TESTING', return_value=True):
      event = self._KLASS(
          task_config.get_event_setting(self._KLASS.section_name()),
          last_exec_client.get_last_execute_time(self._KLASS.KEYWORD))
      self.assertEqual(event.target_exec_utc, self.utc_now)
      self.assertEqual(event.last_exec_utc, self.utc_now)
      self.assertEqual(event.since_date, self.utc_now)
      self.assertFalse(event.always_handle)
      self.assertTrue(event.should_handle)
