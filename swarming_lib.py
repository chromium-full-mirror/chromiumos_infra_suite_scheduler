# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for kicking off tests via swarming service."""

import collections
import logging

import build_lib
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
# In builder, the timeout for swarming execution is often 1 hour longer than
# the timeout of suite. However, we pass in create_and_return for every
# run_suite.py call for suite-scheduler, which means it doesn't need to be
# consistent with the suite timeout. So here let's just follow the parameters
# used by builder in chromite to make sure
# 1) it's enough to call run_suite.py then return.
# 2) it's not too long even if some suites' timeout in suite_scheduler.ini
# is 1 week.
_EXECUTION_TIMEOUT_HOURS = {
    'arc-cts-qual': 49,
    'arc-gts-qual': 49,
}
_EXECUTION_DEFAULT_TIMEOUT_HOUR = 2

# When a task is about to be killed, it will have a grace period.
_GRACE_PERIOD_SECONDS = 30

# The expiration seconds for a swarming task.
_TASK_EXPIRATION_SECONDS = 20 * 60

# Keys in raw swarming requests.
USER = 'suite_scheduler'
PROPERTY = 'properties'
DIMENSION = 'dimensions'
KEY = 'key'
VALUE = 'value'
ENV = 'env'


class SwarmingRunError(Exception):
  """Raised when interactions with swarming server fail."""


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

    Returns:
      A swarming task ID if it's successfully created.

    Raises:
      SwarmingRunError: if failing to create swarming task.
    """
    final_build = self._get_final_build(**task_params)
    if final_build == 'None':
      raise SwarmingRunError('No proper build in task params: %r' %
                             task_params)

    suite_name = task_params['suite']
    task_name = '%s-%s' % (final_build, suite_name)
    tags = ['suite:%s' % task_params['suite']]
    tags.append('priority:%s' % task_params['priority'])
    tags.append('board:%s' % task_params['board'])
    tags.append('build:%s' % final_build)
    tags.append('task_name:%s' % task_name)

    command = self._form_run_suite_command(final_build, **task_params)
    execution_timeout_secs = self._get_execution_timeout(suite_name)
    raw_request = self._form_swarming_request(
        command, task_name, tags, int(task_params['priority']),
        execution_timeout_secs)
    logging.debug(raw_request)
    return self._client.create_task(request=raw_request)

  def dummy_run(self):
    """Perform a dummy run to swarming proxy service."""
    tags = ['task_name:dummy_run']
    execution_timeout_secs = self._get_execution_timeout('fake_suite')
    raw_request = self._form_swarming_request(
        [self.RUN_SUITE_PATH, '--do_nothing'],
        DUMMY_TASK_NAME, tags, DUMMY_PRIORITY, execution_timeout_secs)
    logging.debug(raw_request)
    return self._client.create_task(request=raw_request)

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

  def _get_execution_timeout(self, suite_name):
    """Get execution timeout for suite.

    Args:
      suite_name: the name of the suite to be kicked off.

    Returns:
      A timeout represented by seconds.
    """
    return 60 * 60 * _EXECUTION_TIMEOUT_HOURS.get(
        suite_name, _EXECUTION_DEFAULT_TIMEOUT_HOUR)

  def _get_final_build(self, **task_params):
    """Get the final build to kick off on a lab DUT.

    Args:
      **task_params: The parameters of a task got from suite queue.

    Returns:
      A string representing the build to run.
    """
    cros_build = task_params[build_lib.BuildVersionKey.CROS_VERSION]
    android_build = task_params[
        build_lib.BuildVersionKey.ANDROID_BUILD_VERSION]
    testbed_build = task_params[
        build_lib.BuildVersionKey.TESTBED_BUILD_VERSION]
    return cros_build or android_build or testbed_build

  def _form_run_suite_command(self, final_build, **task_params):
    """Form the swarming call command based on task_params.

    Args:
      final_build: The build to kick off on a DUT.
      **task_params: the parameters of a task got from suite queue.

    Returns:
      A string command.
    """
    fw_rw_build = task_params[build_lib.BuildVersionKey.FW_RW_VERSION]
    fw_ro_build = task_params[build_lib.BuildVersionKey.FW_RO_VERSION]

    timeout_mins = (task_params['timeout_mins'] or
                    task_params['timeout'] * 60)
    max_runtime_mins = (task_params['max_runtime_mins'] or
                        task_params['timeout'] * 60)

    command = [self.RUN_SUITE_PATH,
               '--build', final_build,
               '--board', task_params['board'],
               '--suite_name', task_params['suite'],
               '--pool', task_params['pool'],
               '--priority', task_params['priority'],
               '--timeout_mins', str(timeout_mins),
               '--max_runtime_mins', str(max_runtime_mins),
               '--no_wait', task_params['no_wait_for_results'],
               '--test_source_build', task_params['test_source_build'],
               '--retry', task_params['job_retry']]

    # Swarming calls from suite_scheduler should creat and return immediately.
    command.extend(['-c'])

    if task_params['force'] != 'True':
      command.extend(['--pre_check'])

    if task_params['num'] != 'None':
      command.extend(['--num', task_params['num']])

    if fw_rw_build != 'None':
      command.extend(['--firmware_rw_build', fw_rw_build])

    if fw_ro_build != 'None':
      command.extend(['--firmware_ro_build', fw_ro_build])

    return command

  def _form_swarming_request(self, command, task_name, tags, priority,
                             execution_timeout_secs):
    """Form a raw request which will be sent to swarming API.

    Args:
      command: the command to be run by swarming bot.
      task_name: the name of the swarming task.
      tags: the tags of the to-be-run swarming task.
      priority: the priority of the to-be-run swarming task.
      execution_timeout_secs: the execution timeout seconds for swarming call.

    Returns:
      A json-compatible dict that can be parsed by swarming API.
    """
    properties = TaskProperties(
        command=command,
        dimensions=self.DIMENSIONS,
        env={},
        execution_timeout_secs=execution_timeout_secs,
        grace_period_secs=_GRACE_PERIOD_SECONDS,
        idempotent=False,
        io_timeout_secs=execution_timeout_secs)
    task_request = NewTaskRequest(
        expiration_secs=_TASK_EXPIRATION_SECONDS,
        name=task_name,
        priority=priority,
        properties=properties,
        tags=tags,
        user=USER)
    return _to_raw_request(task_request)


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
