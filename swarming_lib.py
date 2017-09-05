# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for kicking off tests via swarming service."""

import collections

import constants
import rest_client


# dummy swarming task name
DUMMY_TASK_NAME = 'suite_scheduler_dummy_run'

# The priority for dummy swarming task, make it highest.
DUMMY_PRIORITY = 100

# Representing swarming task properties, coming from chrome_infra repo:
# ./appengine/swarming/swarming_rpcs.py.
TaskProperties = collections.namedtuple(
    'TaskProperties',
    [
        'command',
        'dimensions',
        'env',
        'execution_timeout_secs',
        'grace_period_secs',
        'idempotent',
        'io_timeout_secs',
    ])


# Representing a new swarming task request, coming from chrome_infra repo:
# ./appengine/swarming/swarming_rpcs.py.
NewTaskRequest = collections.namedtuple(
    'NewTaskRequest',
    [
        'expiration_secs',
        'name',
        'priority',
        'properties',
        'tags',
        'user',
    ])

# Swarming tasks information.
SwarmingTaskInfo = collections.namedtuple(
    'SwarmingTaskInfo',
    [
        'name',
        'state',
        'bot_id',
        'created_ts',
    ])

# The theoretical maximum time for executing a swarming task.
_EXECUTION_TIMEOUT_SECONDS = 5 * 60

# When a task is about to be killed, it will have a grace period.
_GRACE_PERIOD_SECONDS = 30

# The expiration seconds for a swarming task.
_TASK_EXPIRATION_SECONDS = 20 * 60

# Keys in raw swarming requests.
PROPERTY = 'properties'
DIMENSION = 'dimensions'
KEY = 'key'
VALUE = 'value'
ENV = 'env'


class SwarmingRunner(object):
  """A class capable of connecting to chromeos-proxy swarming server."""

  SERVICE_URL = 'https://chromeos-proxy.appspot.com/_ah/api'
  RUN_SUITE_PATH = '/usr/local/autotest/site_utils/run_suite.py'
  DIMENSIONS = {'os': 'Ubuntu-14.04', 'pool': 'suite-scheduler'}

  def __init__(self):
    self._client = rest_client.SwarmingRestClient(
        rest_client.BaseRestClient(
            constants.RestClient.SWARMING_CLIENT.scopes,
            constants.RestClient.SWARMING_CLIENT.service_name,
            constants.RestClient.SWARMING_CLIENT.service_version),
        self.SERVICE_URL)

  def run(self, **task_params):
    """Perform a run to swarming proxy service.

    Args:
      **task_params: the suite params to run.
    """
    # TODO(xixuan): add real logic to kick off a suite here.
    pass

  def dummy_run(self):
    """Perform a dummy run to swarming proxy service."""
    tags = ['task_name:dummy_run']
    properties = TaskProperties(
        command=[self.RUN_SUITE_PATH, '--do_nothing'],
        dimensions=self.DIMENSIONS,
        env={},
        execution_timeout_secs=_EXECUTION_TIMEOUT_SECONDS,
        grace_period_secs=_GRACE_PERIOD_SECONDS,
        idempotent=False,
        io_timeout_secs=_EXECUTION_TIMEOUT_SECONDS)
    task_request = NewTaskRequest(
        expiration_secs=_TASK_EXPIRATION_SECONDS,
        name=DUMMY_TASK_NAME,
        priority=DUMMY_PRIORITY,
        properties=properties,
        tags=tags,
        user='suite_scheduler')
    return self._client.create_task(
        request=_to_raw_request(task_request))

  def query_task(self, task_id):
    """Get a kicked-off task's status.

    Args:
      task_id: an id of a swarming task.

    Returns:
      a SwarmingTaskInfo object.
    """
    response = self._client.get_task_result(task_id)
    task_info_dict = {k: response.get(k) for k in SwarmingTaskInfo._fields}
    return SwarmingTaskInfo(**task_info_dict)


def _namedtuple_to_dict(value):
  """Recursively converts a namedtuple to a dict.

  Args:
    value: a namedtuple object.

  Returns:
    A dict object with the same value.
  """
  out = dict(value._asdict())
  for k, v in out.iteritems():
    if hasattr(v, '_asdict'):
      out[k] = _namedtuple_to_dict(v)
    elif isinstance(v, (list, tuple)):
      l = []
      for elem in v:
        if hasattr(elem, '_asdict'):
          l.append(_namedtuple_to_dict(elem))
        else:
          l.append(elem)
      out[k] = l

  return out


def _to_raw_request(request):
  """Returns the json-compatible dict expected by the server.

  Args:
    request: a NewTaskRequest object.

  Returns:
    A json-compatible dict, which could be parsed by swarming proxy
    service.
  """
  out = _namedtuple_to_dict(request)
  out[PROPERTY][DIMENSION] = [
      {KEY: k, VALUE: v}
      for k, v in out[PROPERTY][DIMENSION].iteritems()
  ]
  out[PROPERTY][DIMENSION].sort(key=lambda x: x[KEY])
  out[PROPERTY][ENV] = [
      {KEY: k, VALUE: v}
      for k, v in out[PROPERTY][ENV].iteritems()
  ]
  out[PROPERTY][ENV].sort(key=lambda x: x[KEY])
  return out
