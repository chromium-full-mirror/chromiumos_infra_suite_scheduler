# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for task_executor unittests."""
# pylint: disable=g-bad-import-order

import mock
import os
import sys
import unittest

import task_executor

from google.appengine.api import taskqueue
from google.appengine.ext import testbed


class FakeSwarmingLib(object):

  def __init__(self, success_num=sys.maxint):
    self.success_num = success_num

  def run(self, **suite_kwargs):
    if int(suite_kwargs.get('num', 0)) > self.success_num:
      raise ValueError('test')


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

  def testBatchExecuteTaskSuccessfully(self):
    """Test task_executor successfully execute tasks in batch."""
    suite_kwargs = {'suite': 'fake_suite'}
    extra_num = 10
    for i in range(task_executor.BATCH_SIZE + extra_num):
      suite_kwargs['num'] = i + 1
      task_executor.push(task_executor.SUITES_QUEUE, **suite_kwargs)

    # Before batch_execute
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), task_executor.BATCH_SIZE + extra_num)
    with mock.patch('swarming_lib.SwarmingRunner',
                    return_value=FakeSwarmingLib()):
      task_processor = task_executor.TaskProcessor(task_executor.SUITES_QUEUE)
      task_processor.batch_execute()
      # After batch_execute succeeds, only extra_num tasks left.
      tasks = self.taskqueue_stub.get_filtered_tasks()
      self.assertEqual(len(tasks), extra_num)

  def testBatchExecuteTaskFailedSwarmingTotally(self):
    """Test task_executor fails at the beginning, and no tasks are deleted."""
    suite_kwargs = {'suite': 'fake_suite'}
    extra_num = 10
    for i in range(task_executor.BATCH_SIZE + extra_num):
      suite_kwargs['num'] = i + 1
      task_executor.push(task_executor.SUITES_QUEUE, **suite_kwargs)

    # Before batch_execute
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), task_executor.BATCH_SIZE + extra_num)
    with mock.patch('swarming_lib.SwarmingRunner',
                    return_value=FakeSwarmingLib(0)):
      task_processor = task_executor.TaskProcessor(task_executor.SUITES_QUEUE)
      self.assertRaises(ValueError, task_processor.batch_execute)
      # After batch_execute fails, no tasks are deleted from task queue.
      tasks = self.taskqueue_stub.get_filtered_tasks()
      self.assertEqual(len(tasks), task_executor.BATCH_SIZE + extra_num)

  def testBatchExecuteTaskFailedSwarmingPartially(self):
    """Test task_executor fails halfway, and only executed tasks are deleted."""
    suite_kwargs = {'suite': 'fake_suite'}
    extra_num = 10
    success_num = 50
    for i in range(task_executor.BATCH_SIZE + extra_num):
      suite_kwargs['num'] = i + 1
      task_executor.push(task_executor.SUITES_QUEUE, **suite_kwargs)

    # Before batch_execute
    tasks = self.taskqueue_stub.get_filtered_tasks()
    self.assertEqual(len(tasks), task_executor.BATCH_SIZE + extra_num)
    with mock.patch('swarming_lib.SwarmingRunner',
                    return_value=FakeSwarmingLib(success_num)):
      task_processor = task_executor.TaskProcessor(task_executor.SUITES_QUEUE)
      self.assertRaises(ValueError, task_processor.batch_execute)
      # After batch_execute fails, no tasks are deleted from task queue.
      tasks = self.taskqueue_stub.get_filtered_tasks()
      self.assertEqual(len(tasks),
                       task_executor.BATCH_SIZE - success_num + extra_num)

  def testBatchExecuteTaskFailedLeasing(self):
    """Test task_executor fails to lease task."""
    suite_kwargs = {'suite': 'fake_suite'}
    task_executor.push(task_executor.SUITES_QUEUE, **suite_kwargs)

    with mock.patch('swarming_lib.SwarmingRunner',
                    return_value=FakeSwarmingLib(False)):
      task_processor = task_executor.TaskProcessor('nonExistentQueue')
      self.assertRaises(taskqueue.UnknownQueueError,
                        task_processor.batch_execute)
      # After batch_execute fails, no tasks are deleted from task queue.
      tasks = self.taskqueue_stub.get_filtered_tasks()
      self.assertEqual(len(tasks), 1)


if __name__ == '__main__':
  unittest.main()
