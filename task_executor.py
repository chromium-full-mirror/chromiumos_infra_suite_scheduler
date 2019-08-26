# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for executing tasks queued by suite scheduler."""
# pylint: disable=g-bad-import-order

import ast
import logging

import buildbucket
import constants
import global_config
import swarming_lib

import apiclient
from google.appengine.api import taskqueue
from google.appengine.runtime import apiproxy_errors


SUITES_QUEUE = 'suitesQueue'
BATCH_SIZE = 100


class TaskProcessor(object):
  """A class capable of executing tasks by kicking off suites.

  This class fetches tasks from pullqueue, and kicking off suites
  represented by tasks' params through ChromeOS swarming proxy server.
  """

  def __init__(self, queue_name, afe_server, skylab_swarming_server):
    """Initialize a task executor for further pulling & execution.

    Args:
      queue_name: The name of a pull queue.
      afe_server: A string of the address for the afe_server.
      skylab_swarming_server: A string of swarming server url for skylab.
    """
    self.queue = taskqueue.Queue(queue_name)
    self.swarming = swarming_lib.SwarmingRunner(
        afe_server, skylab_swarming_server)
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
          try:
            params = task.extract_params()
            self._execute(**params)

            executed_tasks.append(task)
          except (ValueError, swarming_lib.SwarmingRunError,
                  apiclient.errors.HttpError) as e:
            logging.exception('Failed to kick off %r', params)
      finally:
        if executed_tasks:
          logging.info('Successfully kicking %d tasks', len(executed_tasks))
          self.queue.delete_tasks(executed_tasks)

  def _execute(self, **params):
    """A wrapper to execute each single task."""
    # No dummy run for frontdoor enabled test.
    is_frontdoor = ast.literal_eval(params.get('is_frontdoor', 'False'))
    if is_frontdoor:
      return self.test_platform_client.run(**params)

    # Test environment.
    if global_config.GAE_TESTING:
      self.swarming.dummy_run(**params)
      return
    # Production environment.
    return self.swarming.run(**params)

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
