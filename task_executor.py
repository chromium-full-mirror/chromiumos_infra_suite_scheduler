# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for executing tasks queued by suite scheduler."""
# pylint: disable=g-bad-import-order

import collections
import logging

import buildbucket
import constants

import apiclient
from google.appengine.api import taskqueue
from google.appengine.runtime import apiproxy_errors


SUITES_QUEUE = 'suitesQueue'
BATCH_SIZE = 100

Options = collections.namedtuple('Options',
                                 ['batch_size', 'multirequest_size'])

_DEFAULT_OPTIONS = Options(
    batch_size=BATCH_SIZE,
    multirequest_size=constants.Buildbucket.MULTIREQUEST_SIZE,
)


class TaskProcessor(object):
  """A class capable of executing tasks by kicking off suites.

  This class fetches tasks from pullqueue, and kicking off suites
  represented by tasks' params through ChromeOS swarming proxy server.
  """

  def __init__(self, queue_name, options=_DEFAULT_OPTIONS):
    """Initialize a task executor for further pulling & execution.

    Args:
      queue_name: The name of a pull queue.
      options: Options to configure the task processor.
    """
    self.queue = taskqueue.Queue(queue_name)
    self._options = options
    # Schedule tests to PROD_BUILDER if in production project, otherwise use
    # STAGING_BUILDER.
    builder = constants.Buildbucket.STAGING_BUILDER
    if (constants.environment() == constants.RunningEnv.ENV_PROD and
        constants.application_id() == constants.AppID.PROD_APP):
      builder = constants.Buildbucket.PROD_BUILDER
    self.test_platform_client = buildbucket.TestPlatformClient(
        constants.Buildbucket.HOST,
        constants.Buildbucket.PROJECT,
        constants.Buildbucket.BUCKET,
        builder)

  def batch_execute(self):
    """Execute tasks."""
    executed_tasks_count = 0
    while (executed_tasks_count + self._options.multirequest_size <=
           self._options.batch_size):
      try:
        tasks = self.queue.lease_tasks_by_tag(
            3600, self._options.multirequest_size, deadline=60)
      except (taskqueue.UnknownQueueError,
              taskqueue.TransientError,
              apiproxy_errors.DeadlineExceededError) as e:
        logging.exception(e)
        raise

      executed_tasks = []
      if not tasks:
        return

      try:
        executed_tasks.extend(
            self.test_platform_client.multirequest_run(tasks, tasks[0].tag))
      except (ValueError,
              buildbucket.BuildbucketRunError,
              apiclient.errors.HttpError) as e:
        logging.exception('Failed to kick off %d tasks for suite %s',
                          len(tasks), tasks[0].tag)
      finally:
        if executed_tasks:
          executed_tasks_count += len(executed_tasks)
          logging.info('Successfully kicking %d tasks for suite %s',
                       len(executed_tasks), tasks[0].tag)
          self.queue.delete_tasks(executed_tasks)

  def purge(self):
    """Purge the entire tasks in the task queue."""
    self.queue.purge()


def push(queue_name, tag=None, **suite_kwargs):
  """Push suites to suite queue for later kickoff.

  Args:
    queue_name: the name of a pull queue.
    tag: tag of a pull queue task.
    **suite_kwargs: the args for a suite to kick off.
  """
  queue = taskqueue.Queue(queue_name)
  queue.add(taskqueue.Task(method='PULL', tag=tag, params=suite_kwargs))
