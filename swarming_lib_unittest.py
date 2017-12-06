# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for swarming unittests."""
# pylint: disable=g-bad-import-order

import mock
import os
import unittest

import build_lib
import swarming_lib
import task_executor

from google.appengine.ext import testbed


class SwarmingLibTestCase(unittest.TestCase):

  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.addCleanup(self.testbed.deactivate)

    self.testbed.init_taskqueue_stub(
        root_path=os.path.join(os.path.dirname(__file__)))
    self.taskqueue_stub = self.testbed.get_stub(
        testbed.TASKQUEUE_SERVICE_NAME)

    self.suite_job_parameters = {
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
    }

  def testFormCommandSuccessfully(self):
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      swarming_runner = swarming_lib.SwarmingRunner()
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
      swarming_runner = swarming_lib.SwarmingRunner()
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
      swarming_runner = swarming_lib.SwarmingRunner()
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_command(final_build, **params)
      self.assertNotIn('--model', command)

  def testFormCommandWithEmptyNum(self):
    self.suite_job_parameters['num'] = None
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      swarming_runner = swarming_lib.SwarmingRunner()
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_command(final_build, **params)
      self.assertNotIn('--num', command)

  def testFormCommandWithEmptyFirmware(self):
    self.suite_job_parameters[build_lib.BuildVersionKey.FW_RW_VERSION] = None
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      swarming_runner = swarming_lib.SwarmingRunner()
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
      swarming_runner = swarming_lib.SwarmingRunner()
      params = tasks[0].extract_params()
      self.assertRaises(swarming_lib.SwarmingRunError,
                        swarming_runner.run, **params)

  def testFormRequestSuccessfully(self):
    task_executor.push(task_executor.SUITES_QUEUE, **self.suite_job_parameters)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      swarming_runner = swarming_lib.SwarmingRunner()
      params = tasks[0].extract_params()
      final_build = swarming_runner._get_final_build(**params)
      command = swarming_runner._form_run_suite_command(final_build, **params)
      raw_request = swarming_runner._form_swarming_request(
          command, 'fake_task_name', ['suite:fake_suite'], 10, 100)
      self.assertEqual(raw_request['priority'], 10)
      self.assertEqual(raw_request['name'], 'fake_task_name')
      self.assertEqual(raw_request['tags'], ['suite:fake_suite'])
      self.assertEqual(raw_request['properties']['command'], command)
      self.assertEqual(raw_request['properties']['execution_timeout_secs'], 100)
      self.assertEqual(raw_request['properties']['io_timeout_secs'], 100)

  def testGetExecutionTimeoutForCTS(self):
    with mock.patch('rest_client.SwarmingRestClient',
                    return_value=None):
      suite = 'arc-cts-qual'
      swarming_runner = swarming_lib.SwarmingRunner()
      self.assertEqual(swarming_runner._get_execution_timeout(suite),
                       60 * 60 * swarming_lib._EXECUTION_TIMEOUT_HOURS[suite])

if __name__ == '__main__':
  unittest.main()
