# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for swarming unittests."""
# pylint: disable=g-bad-import-order

import mock
import os
import unittest

import build_lib
import config_reader
import constants
import file_getter
import rest_client
import swarming_lib
import task_executor

from google.appengine.ext import testbed


def _get_suite_job_parameters():
  return {
      'suite': 'fake_suite',
      'board': 'fake_board',
      'model': 'fake_model',
      build_lib.BuildVersionKey.CROS_VERSION: 'fake_cros_build',
      build_lib.BuildVersionKey.FW_RW_VERSION: 'fake_firmware_rw_build',
      build_lib.BuildVersionKey.FW_RO_VERSION: 'fake_firmware_ro_build',
      build_lib.BuildVersionKey.ANDROID_BUILD_VERSION: 'fake_android_build',
      build_lib.BuildVersionKey.TESTBED_BUILD_VERSION: 'fake_testbed_build',
      'num': 1,
      'pool': 'suites',
      'priority': 10,
      'timeout': 10,
      'timeout_mins': 10,
      'max_runtime_mins': 10,
      'no_wait_for_results': True,
      'test_source_build': 'fake_test_source_build',
      'job_retry': False,
      'no_delay': False,
      'force': False,
      'run_prod_code': True,
      'is_skylab': False,
  }


class SwarmingLibTestCase(unittest.TestCase):

  def setUp(self):
    super(SwarmingLibTestCase, self).setUp()

    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.addCleanup(self.testbed.deactivate)

    self.testbed.init_taskqueue_stub(
        root_path=os.path.join(os.path.dirname(__file__)))
    self.taskqueue_stub = self.testbed.get_stub(
        testbed.TASKQUEUE_SERVICE_NAME)

    self.suite_job_parameters = _get_suite_job_parameters()

  def testFormCommandSuccessfully(self):
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_command(final_build, **params)
      self.assertIn('-c', command)
      self.assertIn('--pre_check', command)
      self.assertIn('--firmware_rw_build', command)
      self.assertIn('--firmware_ro_build', command)

  def testFormCommandWithForce(self):
    self.suite_job_parameters['force'] = True
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_command(final_build, **params)
      self.assertNotIn('--pre_check', command)

  def testFormCommandWithEmptyModel(self):
    self.suite_job_parameters['model'] = None
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_command(final_build, **params)
      self.assertNotIn('--model', command)

  def testFormCommandWithEmptyFirmware(self):
    self.suite_job_parameters[build_lib.BuildVersionKey.FW_RW_VERSION] = None
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_command(final_build, **params)
      self.assertNotIn('--firmware_rw_build', command)

  def testNoFinalBuild(self):
    self.suite_job_parameters[build_lib.BuildVersionKey.CROS_VERSION] = None
    self.suite_job_parameters[
        build_lib.BuildVersionKey.ANDROID_BUILD_VERSION] = None
    self.suite_job_parameters[
        build_lib.BuildVersionKey.TESTBED_BUILD_VERSION] = None
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      self.assertRaises(swarming_lib.SwarmingRunError,
                        swarming_runner.run, **params)

  def testFormRequestSuccessfully(self):
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_command(final_build, **params)
      parsed_task_params = swarming_lib.SwarmingTaskParams(
          final_build='',
          task_name='fake_task_name',
          execution_timeout_secs=100,
          tags=['suite:fake_suite'],
          priority=10)
      raw_request = swarming_runner._form_swarming_request(
          command, {}, parsed_task_params)
      self.assertEqual(raw_request['priority'], 10)
      self.assertEqual(raw_request['name'], 'fake_task_name')
      self.assertEqual(raw_request['tags'], ['suite:fake_suite'])
      self.assertEqual(raw_request['properties']['command'], command)
      self.assertEqual(raw_request['properties']['execution_timeout_secs'], 100)
      self.assertEqual(raw_request['properties']['io_timeout_secs'], 100)

  def testTimeout(self):
    self.suite_job_parameters['timeout'] = 96
    self.suite_job_parameters['timeout_mins'] = 20
    # arc-cts-qual has an overhead timeout of 49h.
    self.suite_job_parameters['suite'] = 'arc-cts-qual'
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch.object(rest_client.SwarmingRestClient, 'create_task',
                           return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      swarming_runner.run(**params)
      call_list = rest_client.SwarmingRestClient.create_task.call_args_list
      self.assertEqual(len(call_list), 1)
      # kvargs is always the index 1 element of the call object
      kvargs = call_list[0][1]
      self.assertEqual(
          kvargs['request']['properties']['execution_timeout_secs'],
          49 * 60 * 60)
      command = kvargs['request']['properties']['command']
      self.assertIn('--timeout_mins', command)
      timeout_index = command.index('--timeout_mins') + 1
      self.assertEqual(command[timeout_index], str(96 * 60))
      self.assertIn('--max_runtime_mins', command)
      timeout_index = command.index('--max_runtime_mins') + 1
      self.assertEqual(command[timeout_index], str(96 * 60))


class SkylabSwarmingLibTestCase(unittest.TestCase):

  def setUp(self):
    super(SkylabSwarmingLibTestCase, self).setUp()

    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.addCleanup(self.testbed.deactivate)

    self.testbed.init_taskqueue_stub(
        root_path=os.path.join(os.path.dirname(__file__)))
    self.taskqueue_stub = self.testbed.get_stub(
        testbed.TASKQUEUE_SERVICE_NAME)

    self.suite_job_parameters = _get_suite_job_parameters()
    self.suite_job_parameters['is_skylab'] = 'True'
    self.suite_job_parameters['priority'] = constants.Priorities.POSTBUILD
    self.suite_job_parameters['override_pool'] = ''
    self.suite_job_parameters['override_qs_account'] = ''

  def testFormSkylabCommandSuccessfully(self):
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_skylab_command(
          final_build, **params)
      self.assertNotIn('--create_and_return', command)
      self.assertIn('--firmware_ro_build', command)
      self.assertNotIn('--test_retry', command)
      self.assertNotIn('-c', command)

  def testFormSkylabCommandWithQS(self):
    self.suite_job_parameters['override_pool'] = 'OVERRIDE_POOL'
    self.suite_job_parameters['override_qs_account'] = 'OVERRIDE_QS_ACCOUNT'
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_skylab_command(
          final_build, **params)
      self.assertIn('OVERRIDE_QS_ACCOUNT', command)
      self.assertIn('OVERRIDE_POOL', command)
      self.assertNotIn(self.suite_job_parameters['pool'], command)

  def testFormSkylabCommandWithEmptyQS(self):
    self.suite_job_parameters['override_pool'] = 'OVERRIDE_POOL'
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_skylab_command(
          final_build, **params)
      self.assertNotIn('--quota_account', command)
      self.assertIn('OVERRIDE_POOL', command)
      self.assertNotIn(self.suite_job_parameters['pool'], command)

  def testPriorityConversion(self):
    self._test_priority('25', 260 - 3 * 25)

  def testMaxPriorityCapping(self):
    # The allowed Skylab priority range is [50, 255].
    self._test_priority('0', 255)

  def testMinPriorityCapping(self):
    self._test_priority('80', 50)

  def testInvalidPriority(self):
    with self.assertRaises(swarming_lib.SwarmingRunError):
      self._test_priority('Not an integer')

  def _test_priority(self, afe_priority, expected_skylab_priority=None):
    self.suite_job_parameters['priority'] = afe_priority
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch.object(rest_client.SwarmingRestClient, 'create_task',
                           return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      swarming_runner.run(**params)
      call_list = rest_client.SwarmingRestClient.create_task.call_args_list
      self.assertEqual(len(call_list), 1)
      # kvargs is always the index 1 element of the call object
      kvargs = call_list[0][1]
      self.assertEqual(kvargs['request']['priority'], expected_skylab_priority)

  def testSkylabTimeout(self):
    self.suite_job_parameters['timeout'] = 96
    self.suite_job_parameters['timeout_mins'] = 20
    # arc-cts-qual has an overhead timeout of 49h.
    self.suite_job_parameters['suite'] = 'arc-cts-qual'
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch.object(rest_client.SwarmingRestClient, 'create_task',
                           return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      swarming_runner.run(**params)
      call_list = rest_client.SwarmingRestClient.create_task.call_args_list
      self.assertEqual(len(call_list), 1)
      # kvargs is always the index 1 element of the call object
      kvargs = call_list[0][1]
      # 3d is the max allowed.
      self.assertEqual(
          kvargs['request']['properties']['execution_timeout_secs'],
          3 * 24 * 60 * 60)
      self.assertEqual(
          kvargs['request']['properties']['io_timeout_secs'],
          3 * 24 * 60 * 60)
      command = kvargs['request']['properties']['command']
      self.assertIn('--timeout_mins', command)
      timeout_index = command.index('--timeout_mins') + 1
      self.assertEqual(command[timeout_index], str(3 * 24 * 60))

  def testDefaultSkylabTimeout(self):
    del self.suite_job_parameters['timeout']
    self.suite_job_parameters['timeout_mins'] = 20
    self.suite_job_parameters['suite'] = 'fake-suite'
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch.object(rest_client.SwarmingRestClient, 'create_task',
                           return_value=None):
      lab_config = config_reader.LabConfig(config_reader.ConfigReader(
          file_getter.LAB_CONFIG_FILE))
      afe_server = lab_config.get_dedicated_afe()
      swarming_runner = swarming_lib.SwarmingRunner(
          afe_server, swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
      params = tasks[0].extract_params()
      swarming_runner.run(**params)
      call_list = rest_client.SwarmingRestClient.create_task.call_args_list
      self.assertEqual(len(call_list), 1)
      # kvargs is always the index 1 element of the call object
      kvargs = call_list[0][1]
      # 2h of suite overhead (default) + 20m of task execution.
      self.assertEqual(
          kvargs['request']['properties']['execution_timeout_secs'],
          (2 * 60 + 20) * 60)
      self.assertEqual(
          kvargs['request']['properties']['io_timeout_secs'],
          (2 * 60 + 20) * 60)
      command = kvargs['request']['properties']['command']
      self.assertIn('--timeout_mins', command)
      timeout_index = command.index('--timeout_mins') + 1
      self.assertEqual(command[timeout_index], str(20))


if __name__ == '__main__':
  unittest.main()
