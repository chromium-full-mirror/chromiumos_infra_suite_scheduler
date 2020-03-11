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

Options = collections.namedtuple(
    'Options',
    ['batch_size', 'multirequest_size', 'per_suite_multirequest_size'])

_DEFAULT_OPTIONS = Options(
    batch_size=100,
    multirequest_size=constants.Buildbucket.MULTIREQUEST_SIZE,
    # A limit on the number of tasks included per request for specific suites.
    per_suite_multirequest_size={
        # crbug.com/1028732: Generates too many results to store in BuildBucket
        # output properties.
        'arc-cts': 15,
        'arc-cts-qual': 15,
        'arc-cts-unibuild': 15,
        'arc-gts': 10,
        'crosbolt_perf_perbuild': 15,
        'ent-nightly': 15,
        'faft_bios': 15,
        'graphics_per-day': 10,
        'graphics_per-week': 15,
        'wifi_matfunc': 10,
    })


def new_task_processor():
  """Factory function to create a task processor appropriate to environment."""
  # Schedule tests to PROD_BUILDER if in production project, otherwise use
  # STAGING_BUILDER.
  builder = constants.Buildbucket.STAGING_BUILDER
  if (constants.environment() == constants.RunningEnv.ENV_PROD
      and constants.application_id() == constants.AppID.PROD_APP):
    builder = constants.Buildbucket.PROD_BUILDER
  test_platform_client = buildbucket.TestPlatformClient(
      constants.Buildbucket.HOST, constants.Buildbucket.PROJECT,
      constants.Buildbucket.BUCKET, builder)
  return TaskProcessor(
      queue_name=SUITES_QUEUE,
      test_platform_client=test_platform_client,
      options=_DEFAULT_OPTIONS)


class TaskProcessor(object):
  """A class capable of executing tasks by kicking off suites.

  This class fetches tasks from pullqueue, and kicks off suites
  represented by tasks' params.
  """

  def __init__(self, queue_name, test_platform_client, options):
    """Initialize a task executor for further pulling & execution.

    Args:
      queue_name: The name of a pull queue.
      test_platform_client: A buildbucket.TestPlatformClient object.
      options: Options to configure the task processor.
    """
    self.queue = taskqueue.Queue(queue_name)
    self._options = options
    self.test_platform_client = test_platform_client

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

      if not tasks:
        return

      tasks = self._limit_heavy_tasks(tasks)
      executed_tasks = []
      try:
        executed_tasks.extend(
            self.test_platform_client.multirequest_run(tasks, _suite(tasks)))
      except (ValueError,
              buildbucket.BuildbucketRunError,
              apiclient.errors.HttpError) as e:
        logging.exception('Failed to kick off %d tasks for suite %s',
                          len(tasks), _suite(tasks))
      finally:
        if executed_tasks:
          executed_tasks_count += len(executed_tasks)
          logging.info('Successfully kicking %d tasks for suite %s',
                       len(executed_tasks), _suite(tasks))
          self.queue.delete_tasks(executed_tasks)

  def purge(self):
    """Purge the entire tasks in the task queue."""
    self.queue.purge()

  def _limit_heavy_tasks(self, tasks):
    """Further limits tasks known to cause large load on cros_test_platform."""
    if not tasks:
      return tasks
    limit = self._options.per_suite_multirequest_size.get(
        _suite(tasks),
        self._options.multirequest_size,
    )
    keep = tasks[:limit]
    forget = tasks[limit:]
    for task in forget:
      self.queue.modify_task_lease(task, 0)
    return keep


def push(queue_name, tag=None, **suite_kwargs):
  """Push suites to suite queue for later kickoff.

  Args:
    queue_name: the name of a pull queue.
    tag: tag of a pull queue task.
    **suite_kwargs: the args for a suite to kick off.
  """
  queue = taskqueue.Queue(queue_name)
  queue.add(taskqueue.Task(method='PULL', tag=tag, params=suite_kwargs))


def _suite(tasks):
  return tasks[0].tag
