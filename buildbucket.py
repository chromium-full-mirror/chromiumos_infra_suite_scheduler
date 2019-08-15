# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for interacting with Buildbucket."""

import datetime
import re
import string

import build_lib
import constants
import file_getter

from chromite.api.gen.test_platform import request_pb2
from components import auth
from components.prpc import client as prpc_client
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

  # This is cloned from swarming_lib.py.
  def _get_final_build(self, **kwargs):
    """Get the final build to kick off on a lab DUT.

    Args:
      **kwargs: The parameters of a task loaded from suite queue.

    Returns:
      A string representing the build to run.
    """
    cros_build = kwargs[build_lib.BuildVersionKey.CROS_VERSION]
    android_build = kwargs[build_lib.BuildVersionKey.ANDROID_BUILD_VERSION]
    testbed_build = kwargs[build_lib.BuildVersionKey.TESTBED_BUILD_VERSION]
    return cros_build or android_build or testbed_build

  def _get_scheduling(self, pool, quota):
    """Assign appropriate quota or pool name to scheduling instance.

    Args:
      pool: string pool name (e.g. 'bvt', 'quota').
      quota: string quota account, or None.

    Returns:
      scheduling: A request_pb2.Request.Params.Scheduling instance.
    """
    if quota:
      return request_pb2.Request.Params.Scheduling(quota_account=quota)

    mp = request_pb2.Request.Params.Scheduling.ManagedPool
    if mp.DESCRIPTOR.values_by_name.get(pool) is not None:
      return request_pb2.Request.Params.Scheduling(managed_pool=mp.Value(pool))

    DUT_POOL_PREFIX = r'DUT_POOL_(?P<munged_pool>.+)'
    match = re.match(DUT_POOL_PREFIX, pool)
    if match:
      munged_pool = string.lower(match.group('munged_pool'))
      if NONSTANDARD_POOL_NAMES.get(munged_pool):
        return request_pb2.Request.Params.Scheduling(
            managed_pool=NONSTANDARD_POOL_NAMES.get(munged_pool))

    return request_pb2.Request.Params.Scheduling(unmanaged_pool=pool)

  def _form_test_platform_request(self, final_build, **task_params):
    """Generate ScheduleBuildRequest for calling buildbucket.

    Args:
      final_build: string, the build to run with the suite (e.g.
        'nyan_blaze-release/R69-10895.33.0').
      **task_params: dict, containing the parameters of a task got from suite
        queue.

    Returns:
      A request_pb2 instance.
    """

    pool = task_params.get('override_pool') or task_params['pool']
    quota = task_params.get('override_qs_account')
    scheduling = self._get_scheduling(pool, quota)

    software_dep = request_pb2.Request.Params.SoftwareDependency()
    software_dep.chromeos_build = final_build

    software_attributes = request_pb2.Request.Params.SoftwareAttributes()
    software_attributes.build_target.name = task_params['board']

    metadata = request_pb2.Request.Params.Metadata()
    metadata.test_metadata_url = task_params['test_source_build']

    timeout_mins = int(task_params['timeout_mins'])
    if task_params.get('timeout'):
      timeout_mins = int(task_params['timeout'])
    if timeout_mins > constants.Buildbucket.MAX_SWARMING_TIMEOUT_MINS:
      timeout_mins = constants.Buildbucket.MAX_SWARMING_TIMEOUT_MINS
    td = datetime.timedelta(minutes=timeout_mins)
    params_time = request_pb2.Request.Params.Time()
    params_time.maximum_duration.FromTimedelta(td)

    params = request_pb2.Request.Params(scheduling=scheduling,
                                        software_dependencies=[software_dep],
                                        software_attributes=software_attributes,
                                        metadata=metadata,
                                        time=params_time)

    if task_params['model'] != 'None':
      params.hardware_attributes.model = task_params['model']

    if task_params['job_retry'] == 'True':
      params.retry.allow = True
      params.retry.max = constants.Buildbucket.MAX_RETRY

    fw_rw_build = task_params.get(build_lib.BuildVersionKey.FW_RW_VERSION)
    fw_ro_build = task_params.get(build_lib.BuildVersionKey.FW_RO_VERSION)
    if fw_ro_build:
      build = params.software_dependencies.add()
      build.ro_firmware_build = fw_ro_build
    if fw_rw_build:
      build = params.software_dependencies.add()
      build.rw_firmware_build = fw_rw_build

    test_plan = request_pb2.Request.TestPlan()
    suite = test_plan.suite.add()
    suite.name = task_params['suite']

    return request_pb2.Request(params=params,
                               test_plan=test_plan)

  def run(self, **task_params):
    """Call TestPlatform Builder to schedule a test.

    Args:
      **task_params: The suite parameters to run.

    Raises:
      BuildbucketRunError: if failed to get build info from task parameters.
    """

    final_build = self._get_final_build(**task_params)
    if final_build == 'None':
      raise BuildbucketRunError('No proper build in task params: %r' %
                                task_params)
    req = self._form_test_platform_request(final_build, **task_params)
    req_struct = self._request_pb2_to_struct_pb2(req)
    cred = None
    if (self.running_env == constants.RunningEnv.ENV_STANDALONE or
        self.running_env == constants.RunningEnv.ENV_DEVELOPMENT_SERVER):
      # If running locally, use the staging service account.
      sa_key = self._gen_service_account_key(
          file_getter.STAGING_CLIENT_SECRETS_FILE)
      cred = prpc_client.service_account_credentials(service_account_key=sa_key)
    self.client.ScheduleBuild(self._build_request(req_struct), credentials=cred)

  def dummy_run(self):
    """Perform a dummy run of prpc call to cros_test_platform-dev."""

    req = request_pb2.Request()
    req_struct = self._request_pb2_to_struct_pb2(req)

    # Use the staging service account to authorize the request.
    sa_key = self._gen_service_account_key(
        file_getter.STAGING_CLIENT_SECRETS_FILE)
    cred = prpc_client.service_account_credentials(service_account_key=sa_key)
    return self.client.ScheduleBuild(
        self._build_request(req_struct), credentials=cred)

  # TODO(linxinan): Handle exceptions when fail to transform proto.
  def _request_pb2_to_struct_pb2(self, req):
    """Transform test_platform_request to google struct proto.

    Args:
      req: A request_pb2 instance.

    Returns:
      A struct_pb2 instance.
    """
    json = json_format.MessageToJson(req)
    structpb = struct_pb2.Struct()
    return json_format.Parse(json, structpb, ignore_unknown_fields=True)

  def _build_request(self, req_struct):
    """Generate ScheduleBuildRequest for calling buildbucket.

    Args:
      req_struct: A struct_pb2 instance.

    Returns:
      A ScheduleBuildRequest instance.
    """
    recipe_struct = struct_pb2.Struct(fields={
        'request': struct_pb2.Value(struct_value=req_struct)})
    return rpc_pb2.ScheduleBuildRequest(builder=self.builder,
                                        properties=recipe_struct)

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
