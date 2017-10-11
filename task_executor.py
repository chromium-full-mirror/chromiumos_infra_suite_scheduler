# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for executing tasks queued by suite scheduler."""

import logging

import global_config
import swarming_lib

from google.appengine.api import taskqueue
from google.appengine.runtime import apiproxy_errors


SUITES_QUEUE = 'suitesQueue'
BATCH_SIZE = 100


class TaskProcessor(object):
  """A class capable of executing tasks by kicking off suites.

  This class fetches tasks from pullqueue, and kicking off suites
  represented by tasks' params through ChromeOS swarming proxy server.
  """

  def __init__(self, queue_name):
    """Initialize a task executor for further pulling & execution.

    Args:
      queue_name: the name of a pull queue.
    """
    self.queue = taskqueue.Queue(queue_name)
    self.swarming = swarming_lib.SwarmingRunner()

  def batch_execute(self):
    try:
      tasks = self.queue.lease_tasks(3600, BATCH_SIZE, deadline=60)
    except (taskqueue.UnknownQueueError,
            taskqueue.TransientError,
            apiproxy_errors.DeadlineExceededError) as e:
      logging.exception(e)
      raise

    if tasks:
      executed_tasks = []
      try:
        for task in tasks:
          if global_config.GAE_TESTING:
            self.swarming.dummy_run()
          else:
            self.swarming.run(**task.extract_params())

          executed_tasks.append(task)

      except (ValueError, swarming_lib.SwarmingRunError) as e:
        logging.exception(e)
        raise
      finally:
        if executed_tasks:
          logging.info('Successfully kicking %d tasks', len(executed_tasks))
          self.queue.delete_tasks(executed_tasks)

  def purge(self):
    """Purge the entire tasks in the task queue."""
    self.queue.purge()


def push(queue_name, **suite_kwargs):
  """Push suites to suite queue for later kickoff.

  Args:
    queue_name: the name of a pull queue.
    **suite_kwargs: the args for a suite to kick off.
  """
  queue = taskqueue.Queue(queue_name)
  queue.add(taskqueue.Task(method='PULL', params=suite_kwargs))
