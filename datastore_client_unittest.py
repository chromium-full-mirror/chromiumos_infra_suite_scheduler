# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for datastore unittests."""
# pylint: disable=g-tzinfo-replace,g-bad-import-order

import datetime
import pytz
import unittest

import datastore_client

from google.appengine.ext import ndb
from google.appengine.ext import testbed


class DatastoreTestCase(unittest.TestCase):

  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.addCleanup(self.testbed.deactivate)
    self.testbed.init_datastore_v3_stub()
    self.testbed.init_memcache_stub()
    ndb.get_context().clear_cache()

  def testSetLastExec(self):
    last_exec_store = datastore_client.LastExecutionRecordStore()
    exec_time = datetime.datetime(2017, 8, 1, 0)
    last_exec_store.set_last_execute_time('nightly', exec_time)
    self.assertEqual(last_exec_store.get_last_execute_time('nightly'),
                     exec_time.replace(tzinfo=pytz.utc))

  def testDeleteLastExec(self):
    last_exec_store = datastore_client.LastExecutionRecordStore()
    exec_time = datetime.datetime(2017, 8, 1, 0)
    last_exec_store.set_last_execute_time('nightly', exec_time)
    last_exec_store.del_last_execute_time('nightly')
    self.assertEqual(last_exec_store.get_last_execute_time('nightly'),
                     None)

  def testDeleteLastExecWithNonExistentKey(self):
    last_exec_store = datastore_client.LastExecutionRecordStore()
    last_exec_store.del_last_execute_time('nightly')

  def testGetAllLastExec(self):
    last_exec_store = datastore_client.LastExecutionRecordStore()
    exec_time = datetime.datetime(2017, 8, 1, 0)
    event_types = ['nightly', 'weekly']
    exec_time_records = [datastore_client.LastExecutionRecord(
        key=ndb.Key(datastore_client.LastExecutionRecord, e),
        event_type=e,
        exec_time=exec_time.replace(tzinfo=pytz.utc)) for e in event_types]

    for e in event_types:
      last_exec_store.set_last_execute_time(e, exec_time)

    last_exec_times = last_exec_store.get_all()
    self.assertEqual(last_exec_times, exec_time_records)

  def testDeleteAllLastExec(self):
    last_exec_store = datastore_client.LastExecutionRecordStore()
    exec_time = datetime.datetime(2017, 8, 1, 0)
    event_types = ['nightly', 'weekly']

    for e in event_types:
      last_exec_store.set_last_execute_time(e, exec_time)

    last_exec_store.delete_all()
    for e in event_types:
      self.assertEqual(last_exec_store.get_last_execute_time(e), None)

if __name__ == '__main__':
  unittest.main()
