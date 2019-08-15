# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for interacting with Buildbucket."""
import datetime

import constants
import file_getter

from chromite.api.gen.test_platform import request_pb2
from components.prpc import client as prpc_client
from components import auth

from google.protobuf import duration_pb2, json_format, struct_pb2
from infra_libs.buildbucket.proto import rpc_pb2, build_pb2, common_pb2
from infra_libs.buildbucket.proto.rpc_prpc_pb2 import BuildsServiceDescription

from oauth2client import service_account
from oauth2client.contrib import appengine


NONSTANDARD_POOL_NAMES = {
    'cq': request_pb2.Request.Params.Scheduling.MANAGED_POOL_CQ,
    'bvt': request_pb2.Request.Params.Scheduling.MANAGED_POOL_BVT,
    'suites': request_pb2.Request.Params.Scheduling.MANAGED_POOL_SUITES,
    'cts': request_pb2.Request.Params.Scheduling.MANAGED_POOL_CTS,
    'cts-perbuild': request_pb2.Request.Params.Scheduling.MANAGED_POOL_CTS_PERBUILD,
    'continuous': request_pb2.Request.Params.Scheduling.MANAGED_POOL_CONTINUOUS,
    'arc-presubmit': request_pb2.Request.Params.Scheduling.MANAGED_POOL_ARC_PRESUBMIT,
    'quota': request_pb2.Request.Params.Scheduling.MANAGED_POOL_QUOTA,
}

def _get_client(address):
  """Create a prpc client instance for given address."""
  return prpc_client.Client(address, BuildsServiceDescription)


class TestPlatformClient(object):
  """prpc client for cros_test_platform, aka frontdoor."""

  def __init__(self, address, project, bucket, builder):
    self.client = _get_client(address)
    self.builder = build_pb2.BuilderID(project=project,
                                       bucket=bucket,
                                       builder=builder)
    self.scope = 'https://www.googleapis.com/auth/userinfo.email'
    self.running_env = constants.environment()

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
    """"Transform test_platform_request to google struct proto.

  Args:
   req: A request_pb2 instance.

  Returns:
   A struct_pb2 instance.
  """
    json = json_format.MessageToJson(req)
    structpb = struct_pb2.Struct()
    return json_format.Parse(json, structpb, ignore_unknown_fields=True)

  def _build_request(self, req_struct):
    """"Generate ScheduleBuildRequest for calling buildbucket.

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
    """"Generate credentials to authorize the call.

  Args:
   sa: a string of the path to the service account json file.

  Returns:
   a service account key.
  """
    service_credentials = service_account.ServiceAccountCredentials
    key  = service_credentials.from_json_keyfile_name(sa, self.scope)
    return  auth.ServiceAccountKey(
        client_email=key.service_account_email,
        private_key=key._private_key_pkcs8_pem,
        private_key_id=key._private_key_id)
