# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for task_executor unittests."""
# pylint: disable=g-bad-import-order
# pylint: disable=unused-argument

import collections
import mock
import os
import sys
import unittest

import constants
import task_executor

from google.appengine.api import taskqueue
from google.appengine.ext import testbed


class FakeFrontdoorClient(object):

  # pylint: disable=g-deprecated-member-used
  def __init__(self, success_num=sys.maxint, error_num=0):
    self.success_num = success_num
    self.error_num = error_num
    self.frontdoor_run_count = collections.defaultdict(list)

  def multirequest_run(self, tasks, suite):
    executed_tasks = []
    for task in tasks:
      params = task.extract_params()
      num = int(params.get('num', 0))
      if num > self.success_num and num <= self.success_num + self.error_num:
        raise ValueError('test')
      executed_tasks.append(task)
    self.frontdoor_run_count[suite].append(executed_tasks)
    return executed_tasks


class TaskExecutorTestCase(unittest.TestCase):

  def setUp(self):
    self.testbed = testbed.Testbed()
    self.testbed.activate()
    self.addCleanup(self.testbed.deactivate)

    # root_path must be set the location of queue.yaml.
    # Otherwise, only the 'default' queue will be available.
    self.testbed.init_taskqueue_stub(
        root_path=os.path.join(os.path.dirname(__file__)))
    self.taskqueue_stub = self.testbed.get_stub(
        testbed.TASKQUEUE_SERVICE_NAME)

  def testPushTask(self):
    suite_kwargs = {'suite': 'fake_suite'}
    task_executor.push(task_executor.SUITES_QUEUE, **suite_kwargs)
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), 1)
    self.assertEqual(suite_kwargs, tasks[0].extract_params())

  def testBatchExecuteTask(self):
    """Test task_executor executes tasks not greater than the BATCH_SIZE."""
    extra_num = 10
    for i in range(task_executor.BATCH_SIZE/2):
      suite_kwargs = {'suite': 'foo_suite',
                      'num': i + 1}
      task_executor.push(task_executor.SUITES_QUEUE,
                         tag='foo_suite', **suite_kwargs)
    for i in range(task_executor.BATCH_SIZE/2 + extra_num):
      suite_kwargs = {'suite': 'hoo_suite',
                      'num': i + 1}
      task_executor.push(task_executor.SUITES_QUEUE,
                         tag='hoo_suite', **suite_kwargs)
    with mock.patch('buildbucket.TestPlatformClient',
                    return_value=FakeFrontdoorClient()):
      with mock.patch('global_config.GAE_TESTING', return_value=True):
        task_processor = task_executor.TaskProcessor(
            task_executor.SUITES_QUEUE)
        task_processor.batch_execute()
        # After batch_execute runs, the extra tasks should remain in the queue.
        tasks = self.taskqueue_stub.get_filtered_tasks()
        self.assertEqual(extra_num, len(tasks))

  def testBatchExecuteTaskFailedFrontdoorTotally(self):
    """Test task_executor fails at the beginning, and no tasks are deleted."""
    suite_kwargs = {'suite': 'fake_suite'}
    extra_num = 10
    for i in range(constants.Buildbucket.MULTIREQUEST_SIZE + extra_num):
      suite_kwargs['num'] = i + 1
      task_executor.push(task_executor.SUITES_QUEUE, **suite_kwargs)

    # Before batch_execute
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks),
        constants.Buildbucket.MULTIREQUEST_SIZE + extra_num)
    with mock.patch('buildbucket.TestPlatformClient',
                    return_value=FakeFrontdoorClient(0, error_num=len(tasks))):
      task_processor = task_executor.TaskProcessor(task_executor.SUITES_QUEUE)
      task_processor.batch_execute()
      # After batch_execute, no tasks are deleted from task queue, due
      # to they're all failed to kick off.
      tasks = self.taskqueue_stub.get_filtered_tasks()
      self.assertEqual(len(tasks),
          constants.Buildbucket.MULTIREQUEST_SIZE + extra_num)

  def testBatchExecuteTaskFailedFrontdoorPartially(self):
    """Test task_executor fails halfway, and only executed tasks are deleted."""
    suite_kwargs = {'suite': 'fake_suite'}
    extra_num = 10
    success_num = (extra_num + constants.Buildbucket.MULTIREQUEST_SIZE) / 2
    error_num = extra_num + constants.Buildbucket.MULTIREQUEST_SIZE
    for i in range(constants.Buildbucket.MULTIREQUEST_SIZE + extra_num):
      suite_kwargs['num'] = i + 1
      task_executor.push(task_executor.SUITES_QUEUE, **suite_kwargs)

    # Before batch_execute
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks),
        constants.Buildbucket.MULTIREQUEST_SIZE + extra_num)
    with mock.patch('buildbucket.TestPlatformClient',
                    return_value=FakeFrontdoorClient(success_num, error_num)):
      task_processor = task_executor.TaskProcessor(task_executor.SUITES_QUEUE)
      task_processor.batch_execute()
      # After batch_execute, only failed suites and extra suites are
      # kept in task queue.
      tasks = self.taskqueue_stub.get_filtered_tasks()
      self.assertEqual(len(tasks), error_num)

  def testBatchExecuteTaskFailedLeasing(self):
    """Test task_executor fails to lease task."""
    suite_kwargs = {'suite': 'fake_suite'}
    task_executor.push(task_executor.SUITES_QUEUE, **suite_kwargs)

    with mock.patch('buildbucket.TestPlatformClient',
                    return_value=FakeFrontdoorClient(False)):
      task_processor = task_executor.TaskProcessor('nonExistentQueue')
      self.assertRaises(taskqueue.UnknownQueueError,
                        task_processor.batch_execute)
      # After batch_execute fails, no tasks are deleted from task queue.
      tasks = self.taskqueue_stub.get_filtered_tasks()
      self.assertEqual(len(tasks), 1)


if __name__ == '__main__':
  unittest.main()
