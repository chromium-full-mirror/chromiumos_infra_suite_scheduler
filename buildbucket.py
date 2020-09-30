# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Module for interacting with Buildbucket."""

import collections
import datetime
import logging
import re
import string
import types
import uuid

import analytics
import build_lib
import constants
import file_getter

from chromite.api.gen.test_platform import request_pb2 as ctp_request
from components import auth
from components.prpc import client as prpc_client
from infra_libs.buildbucket.proto import common_pb2 as bb_common_pb2
from infra_libs.buildbucket.proto import rpc_pb2, build_pb2
from infra_libs.buildbucket.proto.rpc_prpc_pb2 import BuildsServiceDescription

from oauth2client import service_account

from google.protobuf import json_format, struct_pb2


GS_PREFIX = 'gs://chromeos-image-archive/'

# The default prpc timeout(10 sec) is too short for the request_id
# to propgate in buildbucket, and could not fully dedup the
# ScheduleBuild request. Increase it while not hitting the default
# GAE deadline(60 sec)
PRPC_TIMEOUT_SEC = 55


def _get_client(address):
  """Create a prpc client instance for given address."""
  return prpc_client.Client(address, BuildsServiceDescription)


class BuildbucketRunError(Exception):
  """Raised when interactions with buildbucket server fail."""


class TestPlatformClient(object):
  """prpc client for cros_test_platform, aka frontdoor."""
  def __init__(self, address, project, bucket, builder):
    self.client = _get_client(address)
    self.builder = build_pb2.BuilderID(project=project,
                                       bucket=bucket,
                                       builder=builder)
    self.scope = 'https://www.googleapis.com/auth/userinfo.email'
    self.running_env = constants.environment()

  def multirequest_run(self, tasks, suite):
    """Call cros_test_platform Builder to schedule a batch of suite tests.

    Args:
      tasks: The suite tasks to run.
      suite: suite name for the batch request.

    Returns:
      List of executed tasks.

    Raises:
      BuildbucketRunError: if failed to get build info from task parameters.
    """
    requests = []
    executed_tasks = []
    counter = collections.defaultdict(int)
    task_executions = []
    for task in tasks:
      try:
        params = task.extract_params()
        if _should_skip(params):
          continue
        req = _form_test_platform_request(params)
        req_json = json_format.MessageToJson(req)
        counter_key = params['board']
        counter_key += '' if params['model'] in [None, 'None'
                                                 ] else ('_' + params['model'])
        counter[counter_key] += 1
        req_name = counter_key
        if counter[counter_key] > 1:
          req_name += '_' + str(counter[counter_key] - 1)
        requests.append('"%s": %s' % (req_name, req_json))
        executed_tasks.append(task)
        if params.get('task_id'):
          task_executions.append(
              analytics.ExecutionTask(params['task_id'], req_name))
      except (ValueError, BuildbucketRunError):
        logging.error('Failed to process task: %r', params)
    if not requests:
      return []
    try:
      requests_json = '{ "requests": { %s } }' % ', '.join(requests)
      req_build = self._build_request(requests_json, _bb_tags(suite))
      logging.debug('Raw request to buildbucket: %r', req_build)

      if (self.running_env == constants.RunningEnv.ENV_STANDALONE
          or self.running_env == constants.RunningEnv.ENV_DEVELOPMENT_SERVER):
        # If running locally, use the staging service account.
        sa_key = self._gen_service_account_key(
            file_getter.STAGING_CLIENT_SECRETS_FILE)
        cred = prpc_client.service_account_credentials(
            service_account_key=sa_key)
      else:
        cred = prpc_client.service_account_credentials()
      resp = self.client.ScheduleBuild(req_build,
                                       credentials=cred,
                                       timeout=PRPC_TIMEOUT_SEC)
      logging.debug('Response from buildbucket: %r', resp)
      for t in task_executions:
        t.update_result(resp)
        try:
          if not t.upload():
            logging.warning('Failed to insert row: %r', t)
        # For any exceptions from BQ, only log it.
        except Exception as e:  #pylint: disable=broad-except
          logging.exception('Failed to insert row: %r, got error: %s', t,
                            str(e))
      return executed_tasks
    except Exception as e:
      logging.debug('Failed to process tasks: %r', tasks)
      logging.exception(str(e))
      return []

  def dummy_run(self):
    """Perform a dummy run of prpc call to cros_test_platform-dev."""

    requests_json = '{ "requests": { "dummy": {} } }'
    req_build = self._build_request(requests_json, tags=None)
    # Use the staging service account to authorize the request.
    sa_key = self._gen_service_account_key(
        file_getter.STAGING_CLIENT_SECRETS_FILE)
    cred = prpc_client.service_account_credentials(service_account_key=sa_key)
    return self.client.ScheduleBuild(req_build,
                                     credentials=cred,
                                     timeout=PRPC_TIMEOUT_SEC)

  def _build_request(self, reqs_json, tags):
    """Generate ScheduleBuildRequest for calling buildbucket.

    Args:
      reqs_json: A json string of requests.
      tags: A list of tags for the buildbucket build.

    Returns:
      A ScheduleBuildRequest instance.
    """
    requests_struct = struct_pb2.Struct()
    recipe_struct = json_format.Parse(reqs_json, requests_struct)
    return rpc_pb2.ScheduleBuildRequest(builder=self.builder,
                                        properties=recipe_struct,
                                        request_id=str(uuid.uuid1()),
                                        tags=tags)

  def _gen_service_account_key(self, sa):
    """Generate credentials to authorize the call.

    Args:
      sa: A string of the path to the service account json file.

    Returns:
      A service account key.
    """
    service_credentials = service_account.ServiceAccountCredentials
    key = service_credentials.from_json_keyfile_name(sa, self.scope)
    return auth.ServiceAccountKey(client_email=key.service_account_email,
                                  private_key=key._private_key_pkcs8_pem,
                                  private_key_id=key._private_key_id)


def _form_test_platform_request(task_params):
  """Generates test_platform.Request proto to send to buildbucket.

  Args:
    task_params: dict containing the parameters of a task from the suite queue.

  Returns:
    A ctp_request.Request instance.
  """
  build = _infer_build_from_task_params(task_params)
  if build == 'None':
    raise BuildbucketRunError('No proper build in task params: %r' %
                              task_params)
  pool = _infer_pool_from_task_params(task_params)
  timeout = _infer_timeout_from_task_params(task_params)

  request = ctp_request.Request()
  params = request.params

  params.scheduling.CopyFrom(_scheduling_for_pool(pool))
  if task_params.get('qs_account') not in ['None', None]:
    params.scheduling.qs_account = task_params.get('qs_account')
  # Quota Scheduler has no concept of priority.
  if (task_params.get('priority') not in ['None', None]
      and not params.scheduling.qs_account):
    params.scheduling.priority = int(task_params['priority'])

  params.software_dependencies.add().chromeos_build = build
  params.software_attributes.build_target.name = task_params['board']

  gs_url = GS_PREFIX + task_params['test_source_build']
  params.metadata.test_metadata_url = gs_url
  params.metadata.debug_symbols_archive_url = gs_url

  params.time.maximum_duration.FromTimedelta(timeout)

  for key, value in _request_tags(task_params, build, pool).iteritems():
    params.decorations.tags.append('%s:%s' % (key, value))

  for d in _infer_user_defined_dimensions(task_params):
    params.freeform_attributes.swarming_dimensions.append(d)

  if task_params['model'] != 'None':
    params.hardware_attributes.model = task_params['model']

  if task_params['job_retry'] == 'True':
    params.retry.allow = True
    params.retry.max = constants.Buildbucket.MAX_RETRY

  fw_rw_build = task_params.get(build_lib.BuildVersionKey.FW_RW_VERSION)
  fw_ro_build = task_params.get(build_lib.BuildVersionKey.FW_RO_VERSION)
  # Skip firmware field if None(unspecified) or 'None'(no such build).
  if fw_ro_build not in (None, 'None'):
    build = params.software_dependencies.add()
    build.ro_firmware_build = fw_ro_build
  if fw_rw_build not in (None, 'None'):
    build = params.software_dependencies.add()
    build.rw_firmware_build = fw_rw_build

  request.test_plan.suite.add().name = task_params['suite']
  return request

def _scheduling_for_pool(pool):
  """Assign appropriate pool name to scheduling instance.

  Args:
    pool: string pool name (e.g. 'MANAGED_POOL_QUOTA', 'wificell').

  Returns:
    scheduling: A ctp_request.Request.Params.Scheduling instance.
  """
  mp = ctp_request.Request.Params.Scheduling.ManagedPool
  if mp.DESCRIPTOR.values_by_name.get(pool) is not None:
    return ctp_request.Request.Params.Scheduling(managed_pool=mp.Value(pool))
  return ctp_request.Request.Params.Scheduling(unmanaged_pool=pool)


# Also see: A copy of this function in swarming_lib.py.
def _infer_build_from_task_params(task_params):
  """Infer the build to install on the DUT for the scheduled task.

  Args:
    task_params: The parameters of a task loaded from suite queue.

  Returns:
    A string representing the build to run.
  """
  cros_build = task_params[build_lib.BuildVersionKey.CROS_VERSION]
  android_build = task_params[build_lib.BuildVersionKey.ANDROID_BUILD_VERSION]
  testbed_build = task_params[build_lib.BuildVersionKey.TESTBED_BUILD_VERSION]
  return cros_build or android_build or testbed_build


def _infer_pool_from_task_params(task_params):
  """Infer the pool to use for the scheduled task.

  Args:
    task_params: The parameters of a task loaded from suite queue.

  Returns:
    A string pool to schedule task in.
  """
  if task_params.get('override_qs_account'):
    return 'DUT_POOL_QUOTA'
  return task_params.get('override_pool') or task_params['pool']


def _infer_timeout_from_task_params(task_params):
  """Infer the timeout for the scheduled task.

  Args:
    task_params: The parameters of a task loaded from suite queue.

  Returns:
    A datetime.timedelta instance for the timeout.
  """
  timeout_mins = int(task_params['timeout_mins'])
  # timeout's unit is hour.
  if task_params.get('timeout'):
    timeout_mins = max(int(task_params['timeout']) * 60, timeout_mins)
  if timeout_mins > constants.Buildbucket.MAX_BUILDBUCKET_TIMEOUT_MINS:
    timeout_mins = constants.Buildbucket.MAX_BUILDBUCKET_TIMEOUT_MINS
  return datetime.timedelta(minutes=timeout_mins)


def _infer_user_defined_dimensions(task_params):
  """Infer the dimensions defined by users.

  Args:
    task_params: The parameters of a task loaded from suite queue.

  Returns:
    A list of strings; an empty list if no dimensions set.

  Raises:
    ValueError: if dimension is not valid.
  """
  result = []
  if task_params.get('dimensions') in (None, 'None'):
    return result
  for d in task_params.get('dimensions').split(','):
    if len(d.split(':')) != 2:
      raise ValueError(
          'Job %s has invalid dimensions: %s' %
          (task_params.get('name'), task_params.get('dimensions')))
    result.append(d)
  return result


def _request_tags(task_params, build, pool):
  """Infer tags to include in cros_test_platform request.

  Args:
    task_params: suite task parameters.
    build: The build included in the request. Must not be None.
    pool: The DUT pool used for the request. Must not be None.

  Returns:
    A dict of tags.
  """
  tags = {
      'build': build,
      'label-pool': pool,
  }
  if task_params.get('board') not in (None, 'None'):
    tags['label-board'] = task_params['board']
  if task_params.get('model') not in (None, 'None'):
    tags['label-model'] = task_params['model']
  if task_params.get('suite') not in (None, 'None'):
    tags['suite'] = task_params['suite']
  return tags


def _get_key_val_from_label(label):
  """A helper to get key and value from the label.

  Args:
    label: A string of label, should be in the form of
      key:value, e.g. 'pool:ChromeOSSkylab'.
  """
  res = label.split(':')
  if len(res) == 2:
    return res[0], res[1]
  logging.warning('Failed to parse the label, %s', label)


def _bb_tags(suite):
  """Get all the tags required for Buildbucket.

  Args:
    suite: A string of suite name being scheduled.

  Returns:
    [bb_common_pb2.StringPair] tags to include the buildbucket request.
  """
  return [bb_common_pb2.StringPair(key='suite', value=suite),
          bb_common_pb2.StringPair(key='user_agent',
                                   value='suite_scheduler')]


def _should_skip(params):
  """Decide whether to skip a task based on env and pool.

  Suite request from staging may still have a small chance to run
  in production. However, for unmanaged pools(e.g. wificell), which
  usually are small, dev traffic is unacceptable.

  Args:
    params: dict containing the parameters of a task got from suite
      queue.

  Returns:
    A boolean; true for suite targetting non-default pools from staging
      env.
  """
  if constants.application_id() == constants.AppID.PROD_APP:
    return False
  return params['pool'] != 'MANAGED_POOL_QUOTA'
