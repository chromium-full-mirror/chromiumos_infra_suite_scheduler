#!/usr/bin/env python2
# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Module for buildbucket unittests."""

import json
import mock
import os
import unittest
import safe_log

import constants
import build_lib
import buildbucket
import task_executor
import file_getter

from chromite.api.gen.test_platform import request_pb2 as ctp_request
from chromite.api.gen.chromiumos.test.api import ctp2_pb2 as ctpv2_request
from chromite.api.gen.test_platform.suite_scheduler import analytics_pb2
from chromite.third_party.infra_libs.buildbucket.proto import build_pb2, builder_common_pb2
from google.appengine.api import taskqueue
from google.appengine.ext import testbed
from google.protobuf import json_format

ADDR = u'http://localhost:1'
FAKE_UUID = 'c78e0bf3-4142-11ea-bc66-88e9fe4c5349'
FAKE_BUILD_ID = 8890493019851395280


def _get_suite_params(board='fake_board',
                      model='fake_model',
                      suite='fake_suite',
                      pool='MANAGED_POOL_QUOTA',
                      cros_build='fake_cros_build',
                      analytics_name=None,
                      cros_image_bucket='None'):
  return {
      'suite': suite,
      'board': board,
      'model': model,
      build_lib.BuildVersionKey.CROS_VERSION: cros_build,
      build_lib.BuildVersionKey.FW_RW_VERSION: 'fake_firmware_rw_build',
      build_lib.BuildVersionKey.FW_RO_VERSION: 'fake_firmware_ro_build',
      build_lib.BuildVersionKey.ANDROID_BUILD_VERSION: 'fake_android_build',
      build_lib.BuildVersionKey.TESTBED_BUILD_VERSION: 'fake_testbed_build',
      'firmware_ro_version': 'fake_firmware_ro_build',
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
      'analytics_name': analytics_name,
      'secondary_targets': '',
      'run_via_cft': True,
      'include_tags': 'a, b, c',
      'exclude_tags': 'e, f, g',
      'include_names': "*",
      'exclude_names': "foo",
      'android_image_version': "11",
      'gms_core_package': "latest_stable",
      'ddd_suite': True,
      'run_via_trv2': True,
      'cros_image_bucket': cros_image_bucket,
      'test_args': 'tast_expr=example.Pass',
      'enable_autotest_sharding': True
  }


def _get_ctpv2_suite_params(build='R80.0.0',
                            targets=[],
                            karbon_filters=[],
                            koffee_filters=[],
                            suite='fake_suite',
                            pool='MANAGED_POOL_QUOTA',
                            analytics_name=None,
                            ddd_suite=False):
  return {
      'build': build,
      'analytics_name': analytics_name,
      'suite': suite,
      'num': 1,
      'pool': pool,
      'priority': 10,
      'timeout': 12,
      'timeout_mins': 4320,
      'max_runtime_mins': 4320,
      'run_via_cft': True,
      'include_tags': 'a, b, c',
      'exclude_tags': 'e, f, g',
      'include_names': "*",
      'exclude_names': "foo",
      'android_image_version': "11",
      'gms_core_package': "latest_stable",
      'ddd_suite': ddd_suite,
      'run_via_trv2': True,
      'run_via_ctpv2': True,
      'targets': json.dumps(targets),
      'karbon_filters': json.dumps(karbon_filters),
      'koffee_filters': json.dumps(karbon_filters),
  }


class FakeTestPlatformClient(object):
  def __init__(self, test):
    self._test = test
    self.called_with_requests = []
    self.error = None

  def ScheduleBuild(self, req, credentials=None, timeout=10):
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
    self.client = buildbucket.TestPlatformClient(ADDR)
    self.addCleanup(patcher.stop)
    self.get_android_boards_list = buildbucket.get_android_boards_list
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.addCleanup(self.testbed.deactivate)
    self.testbed.init_taskqueue_stub(
        root_path=os.path.join(os.path.dirname(__file__)))
    self.taskqueue_stub = self.testbed.get_stub(testbed.TASKQUEUE_SERVICE_NAME)
    self.queue = taskqueue.Queue(task_executor.SUITES_QUEUE)
    _mock_application_id = mock.patch('constants.application_id')
    self.mock_application_id = _mock_application_id.start()
    self.addCleanup(_mock_application_id.stop)
    self.mock_application_id.return_value = constants.AppID.PROD_APP

  def testFormTestPlatformMultiRequestSuccessfully(self):
    suite_kwargs = [_get_suite_params(board=b) for b in ['foo', 'goo']]
    for suite in suite_kwargs:
      task_executor.push(task_executor.SUITES_QUEUE, tag='fake_suite', **suite)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)

    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()

    request_map = self._extract_request_map_from_bb_client()
    request_list = [
        _struct_to_ctp_request(v) for v in request_map.values()
    ]
    request_list.sort(
        key=lambda req: req.params.software_attributes.build_target.name)
    for i, req in enumerate(request_list):
      self.assertEqual(req.params.scheduling.priority, 10)
      self.assertEqual(
          req.params.scheduling.managed_pool,
          ctp_request.Request.Params.Scheduling.MANAGED_POOL_QUOTA)
      # Don't check for exact max timeout to stay DRY.
      # But do check that the maximum is sane.
      self.assertLess(req.params.time.maximum_duration.seconds,
                      2 * 24 * 60 * 60)
      gs_url = ('gs://chromeos-image-archive/%s' %
                suite_kwargs[i]['test_source_build'])

      self.assertEqual(req.params.metadata.test_metadata_url, gs_url)
      self.assertEqual(req.params.metadata.debug_symbols_archive_url, gs_url)
      self.assertEqual(req.test_plan.suite[0].name, suite_kwargs[i]['suite'])
      self.assertEqual(req.params.software_attributes.build_target.name,
                       suite_kwargs[i]['board'])

      gcs_bucket_software_dep = [dep for dep in
                                 req.params.software_dependencies
                                 if dep.chromeos_build_gcs_bucket]
      self.assertEqual(len(gcs_bucket_software_dep), 0)

  def testFormTestPlatformV2RequestSuccessfully(self):
    targets = [[{
      'board': 'fake_board',
      'model': 'fake_model',
      'variant': 'fake_variant',
      'build_type': 'release',
      'test_source_build': 'fake_source_build',
    }]]
    karbon = [
      {
        'container': {
          'hostname': 'us-docker.pkg.dev',
          'project': 'cros-registry/test-service',
          'name': 'fake_filter'
        },
        'dependentContainers': [
          {
            'hostname': 'us-docker.pkg.dev',
            'project': 'cros-registry/test-service',
            'name': 'fake_dependent_filter'
          },
          {
            'hostname': 'us-docker.pkg.dev',
            'project': 'cros-registry/test-service',
            'name': 'fake_dependent_filter_with_digest_and_tags',
            'digest': 'sha256:fakedigest',
            'tags': [
              'fake_tag_1',
              'fake_tag_2'
            ]
          }
        ]
      }
    ]
    suite_kwargs = [_get_ctpv2_suite_params(build=b, targets=targets, karbon_filters=karbon) for b in ['R80.0.0', 'R100.0.0']]
    for suite in suite_kwargs:
      task_executor.push(task_executor.SUITES_QUEUE, tag='__CTPV2__', **suite)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)

    self.client.ctpv2request_run(tasks)
    self._assert_bb_client_called(times=2)

    request_map = self._extract_ctpv2_request_map_from_bb_client()
    request = _struct_to_ctpv2_request(request_map)
    safe_log.info('%s', request)

    self.assertEqual(request.pool, 'MANAGED_POOL_QUOTA')
    self.assertEqual(len(request.targets), 1)
    self.assertEqual(request.targets[0].hw_target.legacy_hw.board, 'fake_board')
    self.assertEqual(request.targets[0].hw_target.legacy_hw.model, 'fake_model')
    self.assertEqual(len(request.targets[0].sw_targets), 1)
    self.assertEqual(request.targets[0].sw_targets[0].legacy_sw.build, 'release')
    self.assertEqual(request.targets[0].sw_targets[0].legacy_sw.variant, 'fake_variant')
    self.assertEqual(request.targets[0].sw_targets[0].legacy_sw.gcs_path, ('gs://chromeos-image-archive/%s' % 'fake_source_build'))
    self.assertEqual(len(request.karbon_filters), 1)
    self.assertEqual(request.suite_request.test_suite.name, 'fake_suite')

  def testGetAndroidBoardsList(self):
    android_boards_list = self.get_android_boards_list(file_getter.TEST_LAB_CONFIG_FILE)
    self.assertEqual(android_boards_list,['pixel6', 'pixel7', 'pixel4', 'pixel5', 'pixel3', 'pixel1']
)

  def testPoolName(self):
    suite_kwargs = [_get_suite_params(board=b) for b in ['foo', 'goo', 'hoo']]
    suite_kwargs[0]['pool'] = 'MANAGED_POOL_CTS'
    suite_kwargs[1]['pool'] = 'wifi'
    for suite in suite_kwargs:
      task_executor.push(task_executor.SUITES_QUEUE, tag='some_suite', **suite)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'some_suite')
    self._assert_bb_client_called()
    request_map = self._extract_request_map_from_bb_client()
    request_list = [
        _struct_to_ctp_request(v) for v in request_map.values()
    ]
    self.assertEqual(len(request_list), 3)
    request_list.sort(
        key=lambda req: req.params.software_attributes.build_target.name)
    self.assertEqual(request_list[0].params.scheduling.managed_pool,
                     ctp_request.Request.Params.Scheduling.MANAGED_POOL_CTS)
    self.assertEqual(request_list[1].params.scheduling.unmanaged_pool,
                     suite_kwargs[1]['pool'])

  def testNoFinalBuild(self):
    suite_kwargs = _get_suite_params()
    suite_kwargs[build_lib.BuildVersionKey.CROS_VERSION] = None
    suite_kwargs[build_lib.BuildVersionKey.ANDROID_BUILD_VERSION] = None
    suite_kwargs[build_lib.BuildVersionKey.TESTBED_BUILD_VERSION] = None

    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite',
                       **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    executed = self.client.multirequest_run(tasks, 'fake_suite')
    self.assertEqual(len(executed), 0)
    self._assert_bb_client_not_called()

  def testShouldSetQsAccountForUnmanagedPool(self):
    suite_kwargs = _get_suite_params(pool='foo')
    suite_kwargs['priority'] = '30'
    suite_kwargs['qs_account'] = 'qs-foo'

    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite',
                       **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    request_map = self._extract_request_map_from_bb_client()
    self.assertEqual(len(request_map), 1)
    req = _struct_to_ctp_request(request_map['fake_board_fake_model'])
    self.assertEqual(req.params.scheduling.qs_account, 'qs-foo')
    # If qs_account is set, priority should be 0, the default value
    # defined by proto3.
    self.assertEqual(req.params.scheduling.priority, 0)

  def testShouldSetQsAccountForManagedPool(self):
    suite_kwargs = _get_suite_params(pool='MANAGED_POOL_QUOTA')
    suite_kwargs['qs_account'] = 'qs-foo'

    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite',
                       **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    request_map = self._extract_request_map_from_bb_client()
    self.assertEqual(len(request_map), 1)
    req = _struct_to_ctp_request(request_map['fake_board_fake_model'])
    self.assertEqual(req.params.scheduling.qs_account, 'qs-foo')
    # If qs_account is set, priority should be 0, the default value
    # defined by proto3.
    self.assertEqual(req.params.scheduling.priority, 0)

  def testShouldSetPriority(self):
    suite_kwargs = _get_suite_params()
    suite_kwargs['priority'] = '30'

    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite',
                       **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    request_map = self._extract_request_map_from_bb_client()
    self._assert_bb_client_called()
    self.assertEqual(len(request_map), 1)
    req = _struct_to_ctp_request(request_map['fake_board_fake_model'])
    self.assertEqual(req.params.scheduling.priority, 30)

  def testRequestWithInvalidTags(self):
    suite_kwargs = [_get_suite_params(board=b) for b in ['foo', 'foo']]

    # test request having None String Tag
    suite_kwargs[0]['model'] = 'None'

    # test request having None Tag
    suite_kwargs[1]['model'] = None

    for suite in suite_kwargs:
      task_executor.push(task_executor.SUITES_QUEUE, tag='fake_suite', **suite)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    executed = self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    self.assertEqual(len(executed), 2)

    request_map = self._extract_request_map_from_bb_client()
    self.assertEqual(len(request_map), 2)
    want = {
        'suite:fake_suite',
        'build:fake_cros_build',
        'label-pool:MANAGED_POOL_QUOTA',
        'label-board:foo',
        'ctp-fwd-task-name:None',
    }
    want_bb = {
        'label-image:fake_cros_build',
        'label-suite:fake_suite',
        'suite:fake_suite',
        'user_agent:suite_scheduler',
    }
    for req_name in ['foo', 'foo_1']:
      req = _struct_to_ctp_request(request_map[req_name])
      req_tags = set([t for t in req.params.decorations.tags])
      self.assertEqual(want, req_tags)
      bb_tags = set([t for t in self._extract_tags_from_bb_client()])
      self.assertEqual(want_bb, bb_tags)

  def testRequestTags(self):
    suite_kwargs = _get_suite_params(
        board='fake_board',
        model='fake_model',
        pool='DUT_POOL_QUOTA',
        suite='fake_suite',
        cros_build='fake_build',
        analytics_name='fake_analytics_name',
    )
    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite',
                       **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    want = {
        'label-board:fake_board',
        'label-model:fake_model',
        'label-pool:DUT_POOL_QUOTA',
        'suite:fake_suite',
        'build:fake_build',
        'analytics_name:fake_analytics_name',
        'ctp-fwd-task-name:None',
    }
    want_bb = {
        'label-suite:fake_suite',
        'label-image:fake_build',
        'suite:fake_suite',
        'user_agent:suite_scheduler',
    }
    request_map = self._extract_request_map_from_bb_client()
    request_list = [
        _struct_to_ctp_request(v) for v in request_map.values()
    ]
    self.assertEqual(len(request_list), 1)
    req = request_list[0]
    req_tags = set([t for t in req.params.decorations.tags])
    self.assertEqual(want, req_tags)
    bb_tags = set([t for t in self._extract_tags_from_bb_client()])
    self.assertEqual(want_bb, bb_tags)

  def testRequestUserDefinedDimensions(self):
    suite_kwargs = _get_suite_params(
        board='fake_board',
        model='fake_model',
        pool='MANAGED_POOL_QUOTA',
        suite='fake_suite',
        cros_build='fake_build',
    )
    suite_kwargs['dimensions'] = 'label-wifi:foo, label-bt:hoo'
    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite',
                       **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    request_map = self._extract_request_map_from_bb_client()
    request_list = [
        _struct_to_ctp_request(v) for v in request_map.values()
    ]
    self.assertEqual(len(request_list), 1)
    req = request_list[0]
    free_dimensions = req.params.freeform_attributes.swarming_dimensions
    self.assertTrue(len(free_dimensions), 2)
    self.assertTrue('label-wifi:foo' in free_dimensions)
    self.assertTrue('label-bt:hoo' in free_dimensions)

  def testRequestInvalidUserDefinedDimensions(self):
    suite_kwargs = _get_suite_params(
        board='fake_board',
        model='fake_model',
        pool='MANAGED_POOL_QUOTA',
        suite='fake_suite',
        cros_build='fake_build',
    )
    suite_kwargs['dimensions'] = 'invalid-dimension'
    task_executor.push(task_executor.SUITES_QUEUE,
                       tag='fake_suite',
                       **suite_kwargs)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_not_called()

  def testTestPlatformRequestWithGCSImageBucket(self):
    bucket_name = "eli"
    suite_kwargs = [_get_suite_params(board='foo', cros_image_bucket=bucket_name)]
    for suite in suite_kwargs:
      task_executor.push(task_executor.SUITES_QUEUE, tag='fake_suite', **suite)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)

    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()

    request_map = self._extract_request_map_from_bb_client()
    request_list = [
        _struct_to_ctp_request(v) for v in request_map.values()
    ]
    request_list.sort(
        key=lambda req: req.params.software_attributes.build_target.name)
    for i, req in enumerate(request_list):
      gs_url = ('gs://%s/%s' %
                (bucket_name, suite_kwargs[i]['test_source_build']))
      self.assertEqual(req.params.metadata.test_metadata_url, gs_url)
      self.assertEqual(req.params.metadata.debug_symbols_archive_url, gs_url)
      expected_metadata_url = gs_url + "/metadata/containers.jsonpb"
      self.assertEqual(req.params.metadata.container_metadata_url, expected_metadata_url)
      self.assertEqual(req.test_plan.suite[0].name, suite_kwargs[i]['suite'])
      self.assertEqual(req.params.software_attributes.build_target.name,
                       suite_kwargs[i]['board'])

      # bit clunky to parse a repeated oneof - we filter out to the
      # chromeos_build_gcs_bucket, then assert a) it only appears once and
      # b) its the right value
      gcs_bucket_software_dep = [dep for dep in
                                 req.params.software_dependencies
                                 if dep.chromeos_build_gcs_bucket]
      self.assertEqual(len(gcs_bucket_software_dep), 1)
      self.assertEqual(gcs_bucket_software_dep[0].chromeos_build_gcs_bucket,
                       bucket_name)

  def _get_client(self, addr):
    self.assertEqual(ADDR, addr)
    return self.fake_client

  def _assert_bb_client_called(self, times=1):
    actual = len(self.fake_client.called_with_requests)
    self.assertEqual(actual, times,
                     "BB client called %s times, expected %s" % (actual, times))

  def _assert_bb_client_not_called(self):
    actual = len(self.fake_client.called_with_requests)
    self.assertEqual(actual, 0,
                     "BB client called %s times, expected 0"% actual)

  def _extract_builder_from_bb_client(self):
    return self.fake_client.called_with_requests[0].builder

  def _extract_request_map_from_bb_client(self):
    return self.fake_client.called_with_requests[0].properties['requests']

  def _extract_ctpv2_request_map_from_bb_client(self):
    return self.fake_client.called_with_requests[0].properties['ctpv2_request']

  def _extract_tags_from_bb_client(self):
    return [
        '%s:%s' % (t.key, t.value)
        for t in self.fake_client.called_with_requests[0].tags
    ]


class TestTaskExecutions(TestPlatformClientTestCase):
  def setUp(self):
    super(TestTaskExecutions, self).setUp()
    _mock_bq_client = mock.patch('rest_client.BigqueryRestClient')
    mock_bq_client = _mock_bq_client.start()
    self.addCleanup(_mock_bq_client.stop)
    self.mock_bq_client = FakeBigqueryRestClient(None,
                                                 project='proj',
                                                 dataset='dataset',
                                                 table='foo')
    mock_bq_client.return_value = self.mock_bq_client

  def testRecordSuccessfulTaskExecution(self):
    suite = _get_suite_params(board='fake_build', model='fake_model')
    suite['task_id'] = FAKE_UUID
    task_executor.push(task_executor.SUITES_QUEUE, tag='fake_suite', **suite)
    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    task_execution = json_format.Parse(
        json.dumps(self.mock_bq_client.rows[0]['json']),
        analytics_pb2.ExecutionTask())
    self.assertEqual(task_execution.queued_task_id, FAKE_UUID)
    self.assertEqual(task_execution.request_tag, 'fake_build_fake_model')
    self.assertEqual(task_execution.response.ctp_build_id, str(FAKE_BUILD_ID))
    self.assertEqual(task_execution.error.error_message, '')

  def testRecordFailedTaskExecution(self):
    suite = _get_suite_params(board='fake_build', model='fake_model')
    suite['task_id'] = FAKE_UUID
    task_executor.push(task_executor.SUITES_QUEUE, tag='fake_suite', **suite)
    self.fake_client.error = "cros_test_platform error"
    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    task_execution = json_format.Parse(
        json.dumps(self.mock_bq_client.rows[0]['json']),
        analytics_pb2.ExecutionTask())
    self.assertEqual(task_execution.queued_task_id, FAKE_UUID)
    self.assertEqual(task_execution.request_tag, 'fake_build_fake_model')
    self.assertEqual(task_execution.response.ctp_build_id, '')
    self.assertEqual(task_execution.error.error_message,
                     self.fake_client.error)

  def testIgnoreTaskWithoutTaskID(self):
    suite = _get_suite_params(board='foo')
    task_executor.push(task_executor.SUITES_QUEUE, tag='fake_suite', **suite)
    self.fake_client.error = "cros_test_platform error"
    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    self.assertEqual(len(self.mock_bq_client.rows), 0)

  def testIgnoreSuiteForUnmanagedPoolInStaging(self):
    self.mock_application_id.return_value = 'suite-scheduler-staging'
    suite = _get_suite_params(pool='foo')
    task_executor.push(task_executor.SUITES_QUEUE, tag='fake_suite', **suite)
    self.fake_client.error = "cros_test_platform error"
    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_not_called()

  def testCustomBuilderTestExecution(self):
    suite = _get_suite_params(board='fake_build', model='fake_model')
    suite['task_id'] = FAKE_UUID
    suite['bb_project'] = 'foo-project'
    suite['bb_bucket'] = 'foo-bucket'
    suite['bb_builder'] = 'foo-builder'
    task_executor.push(task_executor.SUITES_QUEUE, tag='fake_suite', **suite)
    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    self.client.multirequest_run(tasks, 'fake_suite')
    self._assert_bb_client_called()
    self.assertEqual(self._extract_builder_from_bb_client(), builder_common_pb2.BuilderID(
      project="foo-project",
      bucket="foo-bucket",
      builder="foo-builder",
    ))

  def testBuilderExecutionFailsWithMultipleBuckets(self):
    suite1 = _get_suite_params(board='fake_build', model='fake_model')
    suite1['task_id'] = FAKE_UUID
    suite1['bb_project'] = 'foo-project'
    suite1['bb_bucket'] = 'foo-bucket'
    suite1['bb_builder'] = 'foo-builder'

    suite2 = _get_suite_params(board='fake_build', model='fake_model')
    suite2['task_id'] = FAKE_UUID
    suite2['bb_project'] = 'bar-project'
    suite2['bb_bucket'] = 'bar-bucket'
    suite2['bb_builder'] = 'bar-builder'

    task_executor.push(task_executor.SUITES_QUEUE, tag='fake_suite', **suite1)
    task_executor.push(task_executor.SUITES_QUEUE, tag='fake_suite', **suite2)

    tasks = self.queue.lease_tasks_by_tag(
        3600, constants.Buildbucket.MULTIREQUEST_SIZE, deadline=60)
    executed = self.client.multirequest_run(tasks, 'fake_suite')
    self.assertEqual(len(executed), 0)
    self._assert_bb_client_not_called()


class TestGetGCSBucket(unittest.TestCase):
  def testNoPrefixOrSuffix(self):
    task_params = {"cros_image_bucket": "eli"}
    self.assertEqual("eli", buildbucket.get_gs_bucket(task_params))
    self.assertEqual("gs://eli/", buildbucket.get_gs_prefix(task_params))

  def testPrefixNoSuffix(self):
    task_params = {"cros_image_bucket": "gs://eli"}
    self.assertEqual("eli", buildbucket.get_gs_bucket(task_params))
    self.assertEqual("gs://eli/", buildbucket.get_gs_prefix(task_params))

  def testNoPrefixYesSuffix(self):
    task_params = {"cros_image_bucket": "eli/"}
    self.assertEqual("eli", buildbucket.get_gs_bucket(task_params))
    self.assertEqual("gs://eli/", buildbucket.get_gs_prefix(task_params))

  def testPrefixAndSuffix(self):
    task_params = {"cros_image_bucket": "gs://eli/"}
    self.assertEqual("eli", buildbucket.get_gs_bucket(task_params))
    self.assertEqual("gs://eli/", buildbucket.get_gs_prefix(task_params))

  def testNoValue(self):
    task_params = {}
    self.assertEqual("chromeos-image-archive", buildbucket.get_gs_bucket(task_params))
    self.assertEqual("gs://chromeos-image-archive/", buildbucket.get_gs_prefix(task_params))


def _struct_to_ctp_request(struct_pb2):
  """Transform google struct proto to test_platform_request.

  Args:
    struct_pb2: A struct_pb2 instance.

  Returns:
    A ctp_request instance.
  """
  json = json_format.MessageToJson(struct_pb2)
  return json_format.Parse(json, ctp_request.Request())


def _struct_to_ctpv2_request(struct_pb2):
  """Transform google struct proto to ctpv2.

  Args:
    struct_pb2: A struct_pb2 instance.

  Returns:
    A ctpv2_request instance.
  """
  json = json_format.MessageToJson(struct_pb2)
  return json_format.Parse(json, ctpv2_request.CTPv2Request())
