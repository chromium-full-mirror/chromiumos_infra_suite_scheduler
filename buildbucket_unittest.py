#!/usr/bin/env python2
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for buildbucket unittests."""

import json
import mock
import os
import unittest

import constants
import build_lib
import buildbucket
import task_executor

from chromite.api.gen.test_platform import request_pb2
from chromite.api.gen.test_platform.suite_scheduler import analytics_pb2
from google.appengine.api import taskqueue
from google.appengine.ext import testbed
from google.protobuf import json_format
from infra_libs.buildbucket.proto import build_pb2


ADDR = u'http://localhost:1'
FAKE_UUID = 'c78e0bf3-4142-11ea-bc66-88e9fe4c5349'
FAKE_BUILD_ID = 8890493019851395280


def _get_suite_params(board='fake_board',
                      model='fake_model',
                      suite='fake_suite',
                      pool='DUT_POOL_SUITES',
                      cros_build='fake_cros_build'):
  return {
      'suite': suite,
      'board': board,
      'model': model,
      build_lib.BuildVersionKey.CROS_VERSION: cros_build,
      build_lib.BuildVersionKey.FW_RW_VERSION: 'fake_firmware_rw_build',
      build_lib.BuildVersionKey.FW_RO_VERSION: 'fake_firmware_ro_build',
      build_lib.BuildVersionKey.ANDROID_BUILD_VERSION: 'fake_android_build',
      build_lib.BuildVersionKey.TESTBED_BUILD_VERSION: 'fake_testbed_build',
      'num': 1,
      'pool': pool,
      'priority': 10,
      'timeout': 12,
      'timeout_mins': 4320,
      'max_runtime_mins': 4320,
      'no_wait_for_results': True,
      'test_source_build': 'fake_test_source_build',
      'job_retry': False,
      'no_delay': False,
      'force': False,
      'run_prod_code': True,
      'is_skylab': False,
  }


class FakeTestPlatformClient(object):

  def __init__(self, test):
    self._test = test
    self.called_with_requests = []
    self.error = None

  def ScheduleBuild(self, req, credentials=None):
    self.called_with_requests.append(req)
    if self.error:
      return self.error
    return build_pb2.Build(id=FAKE_BUILD_ID)


class FakeBigqueryRestClient(object):

  def __init__(self, rest_client, project=None, dataset=None, table=None):
    """Initialize the mock class."""
    self.table = table
    self.rows = []

  def insert(self, rows):
    self.rows = rows
    return True


class TestPlatformClientTestCase(unittest.TestCase):

  def setUp(self):
    super(TestPlatformClientTestCase, self).setUp()
    self.fake_client = FakeTestPlatformClient(self)
    patcher = mock.patch('buildbucket._get_client',
                         return_value=self._get_client(ADDR))
    patcher.start()
    self.client = buildbucket.TestPlatformClient(ADDR,
                                                 'foo-proj',
                                                 'foo-bucket',
                                                 'foo-builder')
    self.addCleanup(patcher.stop)
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.addCleanup(self.testbed.deactivate)
    self.testbed.init_taskqueue_stub(
        root_path=os.path.join(os.path.dirname(__file__)))
    self.taskqueue_stub = self.testbed.get_stub(
        testbed.TASKQUEUE_SERVICE_NAME)
    self.queue = taskqueue.Queue(task_executor.SUITES_QUEUE)

  def testFormTestPlatformMultiRequestSuccessfully(self):
    suite_kwargs = [_get_suite_params(board=b)
                    for b in ['foo', 'goo']]
    for suite in suite_kwargs:
      task_executor.push(task_executor.SUITES_QUEUE,
                         tag='fake_suite', **suite)

    tasks = self.queue.lease_tasks_by_tag(3600,
        constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)

    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()

    request_map = self._extract_request_map_from_bb_client()
    request_list = [_struct_pb2_to_request_pb2(v)
                    for v in request_map.values()]
    request_list.sort(
        key=lambda req: req.params.software_attributes.build_target.name)
    for i, req in enumerate(request_list):
      self.assertEqual(req.params.scheduling.priority, 10)
      self.assertEqual(req.params.scheduling.managed_pool,
                      request_pb2.Request.Params.Scheduling.MANAGED_POOL_SUITES)
      # Don't check for exact max timeout to stay DRY.
      # But do check that the maximum is sane.
      self.assertLess(req.params.time.maximum_duration.seconds, 2*24*60*60)
      gs_url = ('gs://chromeos-image-archive/%s' %
                suite_kwargs[i]['test_source_build'])
      self.assertEqual(req.params.metadata.test_metadata_url, gs_url)
      self.assertEqual(req.params.metadata.debug_symbols_archive_url, gs_url)
      self.assertEqual(req.test_plan.suite[0].name, suite_kwargs[i]['suite'])
      self.assertEqual(req.params.software_attributes.build_target.name,
                      suite_kwargs[i]['board'])

  def testPoolName(self):
    suite_kwargs = [_get_suite_params(board=b)
                    for b in ['foo', 'goo', 'hoo']]
    suite_kwargs[0]['pool'] = 'cts'
    suite_kwargs[1]['pool'] = 'wifi'
    for suite in suite_kwargs:
      task_executor.push(task_executor.SUITES_QUEUE,
                         tag='some_suite', **suite)

    tasks = self.queue.lease_tasks_by_tag(3600,
        constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'some_suite')
    self._assert_bb_client_called()
    request_map = self._extract_request_map_from_bb_client()
    request_list = [_struct_pb2_to_request_pb2(v)
                    for v in request_map.values()]
    self.assertEqual(len(request_list), 3)
    request_list.sort(
        key=lambda req: req.params.software_attributes.build_target.name)
    self.assertEqual(request_list[0].params.scheduling.managed_pool,
                     request_pb2.Request.Params.Scheduling.MANAGED_POOL_CTS)
    self.assertEqual(request_list[1].params.scheduling.unmanaged_pool,
                     suite_kwargs[1]['pool'])

  def testNoFinalBuild(self):
    suite_kwargs = _get_suite_params()
    suite_kwargs[build_lib.BuildVersionKey.CROS_VERSION] = None
    suite_kwargs[build_lib.BuildVersionKey.ANDROID_BUILD_VERSION] = None
    suite_kwargs[build_lib.BuildVersionKey.TESTBED_BUILD_VERSION] = None

    task_executor.push(task_executor.SUITES_QUEUE,
                         tag='fake_suite', **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(3600,
        constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    executed = self.client.multirequest_run(tasks, 'fake_suite')
    self.assertEqual(len(executed), 0)
    self._assert_bb_client_not_called()

  def testShouldSetQsAccount(self):
    suite_kwargs = _get_suite_params(pool='foo')
    suite_kwargs['priority'] = '30'
    suite_kwargs['qs_account'] = 'qs-foo'

    task_executor.push(
        task_executor.SUITES_QUEUE, tag='fake_suite', **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    request_map = self._extract_request_map_from_bb_client()
    self._assert_bb_client_called()
    self.assertEqual(len(request_map), 1)
    req = _struct_pb2_to_request_pb2(request_map['fake_board_fake_model'])
    self.assertEqual(req.params.scheduling.qs_account, 'qs-foo')
    # If qs_account is set, priority should be 0, the default value
    # defined by proto3.
    self.assertEqual(req.params.scheduling.priority, 0)

  def testShouldNotSetQsAccountForManagedPool(self):
    suite_kwargs = _get_suite_params(pool='DUT_POOL_SUITES')
    suite_kwargs['qs_account'] = 'qs-foo'

    task_executor.push(
        task_executor.SUITES_QUEUE, tag='fake_suite', **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    request_map = self._extract_request_map_from_bb_client()
    self._assert_bb_client_called()
    self.assertEqual(len(request_map), 1)
    req = _struct_pb2_to_request_pb2(request_map['fake_board_fake_model'])
    self.assertEqual(req.params.scheduling.qs_account, '')

  def testShouldSetPriority(self):
    suite_kwargs = _get_suite_params()
    suite_kwargs['priority'] = '30'

    task_executor.push(
        task_executor.SUITES_QUEUE, tag='fake_suite', **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(3600,
        constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    request_map = self._extract_request_map_from_bb_client()
    self._assert_bb_client_called()
    self.assertEqual(len(request_map), 1)
    req = _struct_pb2_to_request_pb2(request_map['fake_board_fake_model'])
    self.assertEqual(req.params.scheduling.priority, 30)

  def testRequestWithInvalidTags(self):
    suite_kwargs = [_get_suite_params(board=b)
                    for b in ['foo', 'foo']]

    # test request having None String Tag
    suite_kwargs[0]['model'] = 'None'

    # test request having None Tag
    suite_kwargs[1]['model'] = None

    for suite in suite_kwargs:
      task_executor.push(task_executor.SUITES_QUEUE,
                         tag='fake_suite', **suite)

    tasks = self.queue.lease_tasks_by_tag(3600,
        constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    executed = self.client.multirequest_run(tasks, 'fake_suite')
    self.assertEqual(len(executed), 2)

    self._assert_bb_client_called()
    request_map = self._extract_request_map_from_bb_client()
    self.assertEqual(len(request_map), 2)
    want = {
      'suite:fake_suite',
      'build:fake_cros_build',
      'label-pool:DUT_POOL_SUITES',
      'label-board:foo',
    }
    want_bb = {
      'suite:fake_suite',
    }
    for req_name in ['foo', 'foo_1']:
      req = _struct_pb2_to_request_pb2(request_map[req_name])
      req_tags = set([t for t in req.params.decorations.tags])
      self.assertEqual(want, req_tags)
      bb_tags = set([t for t in self._extract_tags_from_bb_client()])
      self.assertEqual(want_bb, bb_tags)

  def testRequestTags(self):
    suite_kwargs = _get_suite_params(
        board='fake_board',
        model='fake_model',
        pool='DUT_POOL_SUITES',
        suite='fake_suite',
        cros_build='fake_build',
    )
    suite_kwargs['dimensions'] = 'label-wifi:foo,label-bt:hoo'
    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite', **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(3600,
        constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    want = {
      'label-board:fake_board',
      'label-model:fake_model',
      'label-pool:DUT_POOL_SUITES',
      'suite:fake_suite',
      'build:fake_build',
      'label-wifi:foo',
      'label-bt:hoo'
    }
    want_bb = {
      'suite:fake_suite',
    }
    request_map = self._extract_request_map_from_bb_client()
    request_list = [_struct_pb2_to_request_pb2(v)
                    for v in request_map.values()]
    self.assertEqual(len(request_list), 1)
    req = request_list[0]
    req_tags = set([t for t in req.params.decorations.tags])
    self.assertEqual(want, req_tags)
    bb_tags = set([t for t in self._extract_tags_from_bb_client()])
    self.assertEqual(want_bb, bb_tags)

  def _get_client(self, addr):
    self.assertEqual(ADDR, addr)
    return self.fake_client

  def _assert_bb_client_called(self):
    self.assertEqual(len(self.fake_client.called_with_requests), 1)

  def _assert_bb_client_not_called(self):
    self.assertEqual(len(self.fake_client.called_with_requests), 0)

  def _extract_request_map_from_bb_client(self):
    return self.fake_client.called_with_requests[0].properties['requests']

  def _extract_tags_from_bb_client(self):
    return ['%s:%s' % (t.key, t.value)
            for t  in self.fake_client.called_with_requests[0].tags]


class TestTaskExecutions(TestPlatformClientTestCase):

  def setUp(self):
    super(TestTaskExecutions, self).setUp()
    _mock_bq_client = mock.patch('rest_client.BigqueryRestClient')
    mock_bq_client = _mock_bq_client.start()
    self.addCleanup(_mock_bq_client.stop)
    self.mock_bq_client = FakeBigqueryRestClient(
        None, project='proj', dataset='dataset', table='foo')
    mock_bq_client.return_value = self.mock_bq_client

  def testRecordSuccessfulTaskExecution(self):
    suite = _get_suite_params(board='foo')
    suite['task_id'] = FAKE_UUID
    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite', **suite)
    tasks = self.queue.lease_tasks_by_tag(3600,
        constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    task_execution = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ExecutionTask())
    self.assertEqual(task_execution.queued_task_id, FAKE_UUID)
    self.assertEqual(task_execution.response.ctp_build_id, str(FAKE_BUILD_ID))
    self.assertEqual(task_execution.error.error_message, '')

  def testRecordFailedTaskExecution(self):
    suite = _get_suite_params(board='foo')
    suite['task_id'] = FAKE_UUID
    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite', **suite)
    self.fake_client.error = "cros_test_platform error"
    tasks = self.queue.lease_tasks_by_tag(3600,
        constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    task_execution = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ExecutionTask())
    self.assertEqual(task_execution.queued_task_id, FAKE_UUID)
    self.assertEqual(task_execution.response.ctp_build_id, '')
    self.assertEqual(task_execution.error.error_message, self.fake_client.error)

  def testIgnoreTaskWithoutTaskID(self):
    suite = _get_suite_params(board='foo')
    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite', **suite)
    self.fake_client.error = "cros_test_platform error"
    tasks = self.queue.lease_tasks_by_tag(3600,
        constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    self.assertEqual(len(self.mock_bq_client.rows), 0)


def _struct_pb2_to_request_pb2(struct_pb2):
  """Transform google struct proto to test_platform_request.

  Args:
    struct_pb2: A struct_pb2 instance.

  Returns:
    A request_pb2 instance.
  """
  json = json_format.MessageToJson(struct_pb2)
  return json_format.Parse(json, request_pb2.Request())
