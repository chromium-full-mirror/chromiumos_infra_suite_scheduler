# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for buildbucket unittests."""

import mock
import os
import unittest

import build_lib
import buildbucket
import task_executor

from chromite.api.gen.test_platform import request_pb2
from google.appengine.ext import testbed
from google.protobuf import json_format


ADDR = u'http://localhost:1'


def _get_default_suite_params():
  return _get_suite_params(
    board='fake_board',
    model='fake_model',
    suite='fake_suite',
    pool='DUT_POOL_SUITES',
    cros_build='fake_cros_build',
  )

def _get_suite_params(board, model, suite, pool, cros_build):
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

  def ScheduleBuild(self, req, credentials=None):
    self.called_with_requests.append(req)
    # No test_platform_response proto. Simply return '200, ok'.
    return '200 ok'


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

  def testFormTestPlatformRequestSuccessfully(self):
    tp = _get_default_suite_params()
    self.client.run(**self._marshal_to_tq_params(tp))
    self._assert_bb_client_called()
    req = self._extract_request_from_bb_client()
    self.assertEqual(req.params.scheduling.managed_pool,
                     request_pb2.Request.Params.Scheduling.MANAGED_POOL_SUITES)
    self.assertEqual(req.params.time.maximum_duration.seconds, 165600)
    self.assertEqual(req.params.metadata.test_metadata_url,
                     'gs://chromeos-image-archive/' + tp['test_source_build'])
    self.assertEqual(req.test_plan.suite[0].name, tp['suite'])

  def testNonStandardPoolName(self):
    tp = _get_default_suite_params()
    tp['pool'] = 'cts'
    self.client.run(**self._marshal_to_tq_params(tp))
    self._assert_bb_client_called()
    req = self._extract_request_from_bb_client()
    self.assertEqual(req.params.scheduling.managed_pool,
                     request_pb2.Request.Params.Scheduling.MANAGED_POOL_CTS)

  def testShouldGoUnmanagedPool(self):
    tp = _get_default_suite_params()
    tp['pool'] = 'wifi'
    self.client.run(**self._marshal_to_tq_params(tp))
    self._assert_bb_client_called()
    req = self._extract_request_from_bb_client()
    self.assertEqual(req.params.scheduling.unmanaged_pool, tp['pool'])

  def testShouldSchedulewithQuotaAccount(self):
    tp = _get_default_suite_params()
    tp['override_qs_account'] = 'dummy@foo.com'
    self.client.run(**self._marshal_to_tq_params(tp))
    self._assert_bb_client_called()
    req = self._extract_request_from_bb_client()
    self.assertEqual(req.params.scheduling.quota_account,
                     tp['override_qs_account'])

  def testShouldSetPriority(self):
    tp = _get_default_suite_params()
    tp['priority'] = '30'
    self.client.run(**self._marshal_to_tq_params(tp))
    self._assert_bb_client_called()
    req = self._extract_request_from_bb_client()
    self.assertEqual(req.params.scheduling.priority, 30)

  def testNoFinalBuild(self):
    tp = _get_default_suite_params()
    tp[build_lib.BuildVersionKey.CROS_VERSION] = None
    tp[build_lib.BuildVersionKey.ANDROID_BUILD_VERSION] = None
    tp[build_lib.BuildVersionKey.TESTBED_BUILD_VERSION] = None
    params = self._marshal_to_tq_params(tp)
    self.assertRaises(buildbucket.BuildbucketRunError,
                      self.client.run, **params)
    self._assert_bb_client_not_called()

  def testRequestNoneStringTags(self):
    tp = _get_suite_params(
      board='some_board',
      model='None',
      pool='DUT_POOL_SUITES',
      suite='some_suite',
      cros_build='some_build',
    )
    self.client.run(**self._marshal_to_tq_params(tp))
    self._assert_bb_client_called()
    want = {
      'label-board:some_board',
      'label-pool:DUT_POOL_SUITES',
      'suite:some_suite',
      'build:some_build',
    }
    req = self._extract_request_from_bb_client()
    req_tags = set([t for t in req.params.decorations.tags])
    self.assertEqual(want, req_tags)
    bb_tags = set([t for t in self._extract_tags_from_bb_client()])
    self.assertEqual(want, bb_tags)

  def testRequestNoneTags(self):
    tp = _get_suite_params(
      board='some_board',
      model=None,
      pool='DUT_POOL_SUITES',
      suite='some_suite',
      cros_build='some_build',
    )
    self.client.run(**self._marshal_to_tq_params(tp))
    self._assert_bb_client_called()
    want = {
      'label-board:some_board',
      'label-pool:DUT_POOL_SUITES',
      'suite:some_suite',
      'build:some_build',
    }
    req = self._extract_request_from_bb_client()
    req_tags = set([t for t in req.params.decorations.tags])
    self.assertEqual(want, req_tags)
    bb_tags = set([t for t in self._extract_tags_from_bb_client()])
    self.assertEqual(want, bb_tags)

  def testRequestTags(self):
    tp = _get_suite_params(
      board='some_board',
      model='some_model',
      pool='DUT_POOL_SUITES',
      suite='some_suite',
      cros_build='some_build',
    )
    self.client.run(**self._marshal_to_tq_params(tp))
    self._assert_bb_client_called()
    want = {
      'label-board:some_board',
      'label-model:some_model',
      'label-pool:DUT_POOL_SUITES',
      'suite:some_suite',
      'build:some_build',
    }
    req = self._extract_request_from_bb_client()
    req_tags = set([t for t in req.params.decorations.tags])
    self.assertEqual(want, req_tags)
    bb_tags = set([t for t in self._extract_tags_from_bb_client()])
    self.assertEqual(want, bb_tags)

  def _marshal_to_tq_params(self, suite_params):
    """Marshal given suite parameters to a format returned from taskqueue.

    buildbucket.TestPlatformClient.run() expects arguments pulled from a
    taskqueue. This helper function marshals suite parameters into the format
    they would be in when pulled from a taskqueue.
    """
    task_executor.push(task_executor.SUITES_QUEUE, **suite_params)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    return tasks[0].extract_params()

  def _get_client(self, addr):
    self.assertEqual(ADDR, addr)
    return self.fake_client

  def _assert_bb_client_called(self):
    self.assertEqual(len(self.fake_client.called_with_requests), 1)

  def _assert_bb_client_not_called(self):
    self.assertEqual(len(self.fake_client.called_with_requests), 0)

  def _extract_request_from_bb_client(self):
    return _struct_pb2_to_request_pb2(
        self.fake_client.called_with_requests[0].properties['request'])

  def _extract_tags_from_bb_client(self):
    return ['%s:%s' % (t.key, t.value)
            for t  in self.fake_client.called_with_requests[0].tags]


def _struct_pb2_to_request_pb2(struct_pb2):
  """Transform google struct proto to test_platform_request.

  Args:
    struct_pb2: A struct_pb2 instance.

  Returns:
    A request_pb2 instance.
  """
  json = json_format.MessageToJson(struct_pb2)
  return json_format.Parse(json, request_pb2.Request())
