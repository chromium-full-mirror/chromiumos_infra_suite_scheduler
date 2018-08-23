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

# Representing a swarming task params dict after parsing.
SwarmingTaskParams = collections.namedtuple(
    'SwarmingTaskParams',
    [
        'task_name',
        'final_build',
        'execution_timeout_secs',
        'tags',
        'priority',
    ])

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
    'arc-cts-follower': 10,
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

# Swarming server URLs
CHROMEOS_SWARMING_SERVER = 'https://chromeos-proxy.appspot.com/_ah/api'
CHROME_SWARMING_SERVER = 'https://chrome-swarming.appspot.com/_ah/api'
CHROME_STAGING_SWARMING_SERVER = 'https://chromium-swarm-dev.appspot.com/_ah/api'

# A mapping of priorities for skylab hwtest tasks. In swarming,
# lower number means high priorities. Priority lower than 48 will
# be special tasks. The upper bound for priority is 255.
# Use the same priorities mapping as chromite/lib/constants.py
SKYLAB_HWTEST_PRIORITIES_MAP = {
    constants.Priorities.WEEKLY: 230,
    constants.Priorities.DAILY: 200,
    constants.Priorities.POSTBUILD: 170,
    constants.Priorities.DEFAULT: 140,
}


class SwarmingRunError(Exception):
  """Raised when interactions with swarming server fail."""


class SwarmingRunner(object):
  """A class capable of connecting to chromeos-proxy swarming server."""

  RUN_SUITE_PATH = '/usr/local/autotest/site_utils/run_suite.py'
  RUN_SUITE_SKYLAB_PATH = '/usr/local/autotest/bin/run_suite_skylab'
  DIMENSIONS = {'os': 'Ubuntu-14.04', 'pool': 'suite-scheduler'}
  SKYLAB_DIMENSIONS = {'os': 'Ubuntu-14.04', 'pool': 'ChromeOSSkylab-suite'}

  def __init__(self, afe_server, skylab_swarming_server):
    self._client = rest_client.SwarmingRestClient(
        rest_client.BaseRestClient(
            constants.RestClient.SWARMING_CLIENT.scopes,
            constants.RestClient.SWARMING_CLIENT.service_name,
            constants.RestClient.SWARMING_CLIENT.service_version),
        CHROMEOS_SWARMING_SERVER)
    self._skylab_client = rest_client.SwarmingRestClient(
        rest_client.BaseRestClient(
            constants.RestClient.SWARMING_CLIENT.scopes,
            constants.RestClient.SWARMING_CLIENT.service_name,
            constants.RestClient.SWARMING_CLIENT.service_version),
        skylab_swarming_server)
    self._afe_server = afe_server

  def run(self, **task_params):
    """Perform a run to swarming proxy service.

    Args:
      **task_params: the suite params to run.

    Returns:
      A swarming task ID if it's successfully created.

    Raises:
      SwarmingRunError: if failing to create swarming task.
    """
    # To be compatible with old suite parameters.
    is_skylab = task_params.get('is_skylab', 'False')
    if is_skylab == 'True':
      self._run_with_skylab(**task_params)
    else:
      self._run_with_afe(**task_params)

  def _parse_task_params(self, **task_params):
    """Parse the task params for swarming request."""
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

    return SwarmingTaskParams(
        final_build=final_build,
        execution_timeout_sec=self._get_execution_timeout(suite_name),
        task_name=task_name,
        tags=tags,
        priority=int(task_params['priority']))

  def _run_with_skylab(self, **task_params):
    """Kick off suite to skylab."""
    # TODO(xixuan): deal with the random integer priority for cts suites.
    priority = task_params['priority']
    if priority not in SKYLAB_HWTEST_PRIORITIES_MAP:
      raise SwarmingRunError('Priority %s is not accepted by run_suite_skylab.'
                             % str(priority))

    task_params['priority'] = SKYLAB_HWTEST_PRIORITIES_MAP[priority]

    parsed_task_params = self._parse_task_params(**task_params)
    command = self._form_run_suite_skylab_command(
        parsed_task_params.final_build, **task_params)
    raw_request = self._form_swarming_request(
        command, self.SKYLAB_DIMENSIONS, parsed_task_params)
    logging.debug(raw_request)
    return self._skylab_client.create_task(request=raw_request)

  def _run_with_afe(self, **task_params):
    """Kick off suite to AFE."""
    parsed_task_params = self._parse_task_params(**task_params)
    command = self._form_run_suite_command(
        parsed_task_params.final_build, **task_params)
    raw_request = self._form_swarming_request(
        command, self.DIMENSIONS, parsed_task_params)
    logging.debug(raw_request)
    return self._client.create_task(request=raw_request)

  def dummy_run(self, is_skylab=False):
    """Perform a dummy run to swarming proxy service to AFE."""
    if is_skylab:
      command = [self.RUN_SUITE_SKYLAB_PATH, '--board', 'fake_board', '--build',
                 'fake_build', '--suite_name', 'fake_suite', '--do_nothing']
      dimensions = self.SKYLAB_DIMENSIONS
      client = self._skylab_client
    else:
      command = [self.RUN_SUITE_PATH, '--web', self._afe_server, '--do_nothing']
      dimensions = self.DIMENSIONS
      client = self._client

    dummy_task_params = SwarmingTaskParams(
        final_build='',
        execution_timeout_secs=self._get_execution_timeout('fake_suite'),
        tags=['task_name:dummy_run'],
        task_name=DUMMY_TASK_NAME,
        priority=DUMMY_PRIORITY)
    raw_request = self._form_swarming_request(
        command, dimensions, dummy_task_params)
    logging.debug(raw_request)
    return client.create_task(request=raw_request)

  def query_task(self, task_id, is_skylab=False):
    """Get a kicked-off task's status.

    Args:
      task_id: an id of a swarming task.
      is_skylab: A boolean to indicate whether it's querying task on skylab.

    Returns:
      a SwarmingTaskInfo object.
    """
    client = self._skylab_client if is_skylab else self._client
    response = client.get_task_result(task_id)
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

  def _form_run_suite_skylab_command(self, final_build, **task_params):
    """Form the Skylab swarming call command based on task_params.

    TODO (xixuan): To reduce the refactor work, I keep some duplicated codes
    in both this function and |_form_run_suite_command|. When skylab is fully
    launched, I will remove |_form_run_suite_command| completely.

    Args:
      final_build: The build to run with the suite.
      **task_params: The parameters of a task got from suite queue.

    Returns:
      A list of command to run on swarming.
    """

    fw_rw_build = task_params[build_lib.BuildVersionKey.FW_RW_VERSION]
    fw_ro_build = task_params[build_lib.BuildVersionKey.FW_RO_VERSION]
    timeout_mins = (task_params['timeout_mins'] or
                    task_params['timeout'] * 60)

    command = [self.RUN_SUITE_SKYLAB_PATH,
               '--build', final_build,
               '--board', task_params['board'],
               '--suite_name', task_params['suite'],
               '--pool', task_params['pool'],
               '--priority', task_params['priority'],
               '--timeout_mins', str(timeout_mins),
               '--test_source_build', task_params['test_source_build'],
               '--test_retry', task_params['job_retry']]

    # Swarming calls from suite_scheduler should creat and return immediately.
    command.extend(['--create_and_return'])

    if task_params['force'] != 'True':
      command.extend(['--pre_check'])

    if task_params['model'] != 'None':
      command.extend(['--model', task_params['model']])

    if fw_rw_build != 'None':
      command.extend(['--firmware_rw_build', fw_rw_build])

    if fw_ro_build != 'None':
      command.extend(['--firmware_ro_build', fw_ro_build])

    return command

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
               '--retry', task_params['job_retry'],
               '--web', self._afe_server]

    # Swarming calls from suite_scheduler should creat and return immediately.
    command.extend(['-c'])

    if task_params['force'] != 'True':
      command.extend(['--pre_check'])

    if task_params['model'] != 'None':
      command.extend(['--model', task_params['model']])

    if fw_rw_build != 'None':
      command.extend(['--firmware_rw_build', fw_rw_build])

    if fw_ro_build != 'None':
      command.extend(['--firmware_ro_build', fw_ro_build])

    return command

  def _form_swarming_request(self, command, dimensions, parsed_task_params):
    """Form a raw request which will be sent to swarming API.

    Args:
      command: the command to be run by swarming bot.
      dimensions: A dict indicating the dimensions of the task.
      parsed_task_params: A SwarmingTaskParams object.

    Returns:
      A json-compatible dict that can be parsed by swarming API.
    """
    properties = TaskProperties(
        command=command,
        dimensions=dimensions,
        env={},
        execution_timeout_secs=parsed_task_params.execution_timeout_secs,
        grace_period_secs=_GRACE_PERIOD_SECONDS,
        idempotent=False,
        io_timeout_secs=parsed_task_params.execution_timeout_secs)
    task_request = NewTaskRequest(
        expiration_secs=_TASK_EXPIRATION_SECONDS,
        name=parsed_task_params.task_name,
        priority=parsed_task_params.priority,
        properties=properties,
        tags=parsed_task_params.tags,
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
