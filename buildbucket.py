# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for interacting with Buildbucket."""

import datetime
import logging
import re
import string

import build_lib
import constants
import file_getter

from chromite.api.gen.test_platform import request_pb2
from components import auth
from components.prpc import client as prpc_client
from infra_libs.buildbucket.proto import common_pb2 as bb_common_pb2
from infra_libs.buildbucket.proto import rpc_pb2, build_pb2
from infra_libs.buildbucket.proto.rpc_prpc_pb2 import BuildsServiceDescription

from oauth2client import service_account

from google.protobuf import json_format, struct_pb2


_enum = request_pb2.Request.Params.Scheduling
NONSTANDARD_POOL_NAMES = {
    'cq': _enum.MANAGED_POOL_CQ,
    'bvt': _enum.MANAGED_POOL_BVT,
    'suites': _enum.MANAGED_POOL_SUITES,
    'cts': _enum.MANAGED_POOL_CTS,
    'cts-perbuild': _enum.MANAGED_POOL_CTS_PERBUILD,
    'continuous': _enum.MANAGED_POOL_CONTINUOUS,
    'arc-presubmit': _enum.MANAGED_POOL_ARC_PRESUBMIT,
    'quota': _enum.MANAGED_POOL_QUOTA,
}


GS_PREFIX = 'gs://chromeos-image-archive/'


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

  def run(self, **task_params):
    """Call TestPlatform Builder to schedule a test.

    Args:
      **task_params: The suite parameters to run.

    Raises:
      BuildbucketRunError: if failed to get build info from task parameters.
    """
    req = _form_test_platform_request(task_params)
    req_struct = _request_pb2_to_struct_pb2(req)
    req_build = self._build_request(req_struct, _request_tags_to_bb_tags(req))
    logging.debug('Raw request to buildbucket: %s' % req_build)

    if (self.running_env == constants.RunningEnv.ENV_STANDALONE or
        self.running_env == constants.RunningEnv.ENV_DEVELOPMENT_SERVER):
      # If running locally, use the staging service account.
      sa_key = self._gen_service_account_key(
          file_getter.STAGING_CLIENT_SECRETS_FILE)
      cred = prpc_client.service_account_credentials(service_account_key=sa_key)
    else:
      cred = prpc_client.service_account_credentials()

    resp = self.client.ScheduleBuild(req_build, credentials=cred)
    logging.debug('Response from buildbucket: %s' % resp)

  def dummy_run(self):
    """Perform a dummy run of prpc call to cros_test_platform-dev."""

    req = request_pb2.Request()
    req_struct = _request_pb2_to_struct_pb2(req)

    # Use the staging service account to authorize the request.
    sa_key = self._gen_service_account_key(
        file_getter.STAGING_CLIENT_SECRETS_FILE)
    cred = prpc_client.service_account_credentials(service_account_key=sa_key)
    return self.client.ScheduleBuild(
        self._build_request(req_struct, tags=[]), credentials=cred)

  def _build_request(self, req_struct, tags):
    """Generate ScheduleBuildRequest for calling buildbucket.

    Args:
      req_struct: A struct_pb2 instance.
      tags: A list of tags for the buildbucket build.

    Returns:
      A ScheduleBuildRequest instance.
    """
    recipe_struct = struct_pb2.Struct(fields={
        'request': struct_pb2.Value(struct_value=req_struct)})
    return rpc_pb2.ScheduleBuildRequest(builder=self.builder,
                                        properties=recipe_struct,
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
    return  auth.ServiceAccountKey(
        client_email=key.service_account_email,
        private_key=key._private_key_pkcs8_pem,
        private_key_id=key._private_key_id)


def _form_test_platform_request(task_params):
  """Generate ScheduleBuildRequest for calling buildbucket.

  Args:
    task_params: dict containing the parameters of a task got from suite
        queue.

  Returns:
    A request_pb2 instance.
  """
  build = _infer_build_from_task_params(task_params)
  if build == 'None':
    raise BuildbucketRunError('No proper build in task params: %r' %
                              task_params)
  pool = _infer_pool_from_task_params(task_params)
  timeout = _infer_timeout_from_task_params(task_params)

  request = request_pb2.Request()
  params = request.params

  quota = task_params.get('override_qs_account')
  if quota:
    params.scheduling.quota_account = quota
  else:
    params.scheduling.CopyFrom(_scheduling_for_pool(pool))
  if 'priority' in task_params:
    params.scheduling.priority = int(task_params['priority'])

  params.software_dependencies.add().chromeos_build = build
  params.software_attributes.build_target.name = task_params['board']
  params.metadata.test_metadata_url = (
      GS_PREFIX + task_params['test_source_build']
  )
  params.time.maximum_duration.FromTimedelta(timeout)

  for key, value in _request_tags(task_params, build, pool).iteritems():
    params.decorations.tags.append('%s:%s' % (key, value))

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
    pool: string pool name (e.g. 'bvt', 'quota').

  Returns:
    scheduling: A request_pb2.Request.Params.Scheduling instance.
  """
  mp = request_pb2.Request.Params.Scheduling.ManagedPool
  if mp.DESCRIPTOR.values_by_name.get(pool) is not None:
    return request_pb2.Request.Params.Scheduling(managed_pool=mp.Value(pool))

  DUT_POOL_PREFIX = r'DUT_POOL_(?P<munged_pool>.+)'
  match = re.match(DUT_POOL_PREFIX, pool)
  if match:
    pool = string.lower(match.group('munged_pool'))
  if NONSTANDARD_POOL_NAMES.get(pool):
      return request_pb2.Request.Params.Scheduling(
          managed_pool=NONSTANDARD_POOL_NAMES.get(pool))
  return request_pb2.Request.Params.Scheduling(unmanaged_pool=pool)


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
    timeout_mins = max(int(task_params['timeout'])*60, timeout_mins)
  if timeout_mins > constants.Buildbucket.MAX_BUILDBUCKET_TIMEOUT_MINS:
    timeout_mins = constants.Buildbucket.MAX_BUILDBUCKET_TIMEOUT_MINS
  return datetime.timedelta(minutes=timeout_mins)


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


def _request_tags_to_bb_tags(request):
  """Convert given request_pb.Request tags to buildbucket tags.

  Args:
    request: A request_pb2.Request.

  Returns:
    [bb_common_pb2.StringPair] tags to include the buildbucket request.
  """
  bb_tags = []
  for t in request.params.decorations.tags:
    k, v = t.split(':')
    bb_tag = bb_common_pb2.StringPair()
    bb_tag.key = k
    bb_tag.value = v
    bb_tags.append(bb_tag)
  return bb_tags


# TODO(linxinan): Handle exceptions when fail to transform proto.
def _request_pb2_to_struct_pb2(req):
  """Transform test_platform_request to google struct proto.

  Args:
    req: A request_pb2 instance.

  Returns:
    A struct_pb2 instance.
  """
  json = json_format.MessageToJson(req)
  structpb = struct_pb2.Struct()
  return json_format.Parse(json, structpb, ignore_unknown_fields=True)