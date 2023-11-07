# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Module for building and scheduling a CTPv2 Request."""

import json
import logging

import analytics
import buildbucket

from chromite.third_party.infra_libs.buildbucket.proto import common_pb2 as bb_common_pb2
from chromite.api.gen.chromiumos.test.api import ctp2_pb2 as ctpv2_request

from google.protobuf import json_format

class CTPv2Request(object):
  """ctpv2 request constructor and scheduler."""
  def __init__(self, params):
    self.params = params
    self.req_tags = buildbucket._bb_tags(params['suite'])
    self.req_tags.append(bb_common_pb2.StringPair(
      key='build',
      value=params['build'],
    ))
    self.request = ctpv2_request.CTPv2Request()
    self._form_ctpv2_request()

  def schedule(self, platform_client, cred, builder):
    """Form the scheduling request and send to client.

    Args:
      platform_client: prpc client to build bucket.
      cred: client credentials.
      builder: A builder_common_pb2.BuilderID instance.
    """
    req_json = '{ "ctpv2_request": %s }' % json_format.MessageToJson(self.request)
    req_name = self.params['suite'] + '_' + self.params['build']
    req_build = platform_client._build_request(req_json, self.req_tags, builder)
    logging.debug('Raw request to buildbucket: %r', req_build)

    resp = platform_client.client.ScheduleBuild(req_build,
      credentials=cred,
      timeout=buildbucket.PRPC_TIMEOUT_SEC)
    logging.debug('Response from buildbucket: %r', resp)

    if _key_not_none(self.params, 'task_id'):
      execution_task = analytics.ExecutionTask(self.params['task_id'], req_name)
      execution_task.update_result(resp)
      try:
        if not execution_task.upload():
          logging.warning('Failed to insert row: %r', execution_task)
      # For any exceptions from BQ, only log it.
      except Exception as e:  #pylint: disable=broad-except
        logging.exception('Failed to insert row: %r, got error: %s', execution_task,
                          str(e))

  def _form_ctpv2_request(self):
    """Entry point for creaing the ctpv2 request."""
    self._form_ctpv2_targets()
    self._form_ctpv2_suite_request()
    if _key_not_none(self.params, 'pool'):
      self.request.pool = self.params['pool']
    if _key_not_none(self.params, 'karbon_filters'):
      self._form_ctpv2_filters(self.request.karbon_filters, json.loads(self.params['karbon_filters']))
    if _key_not_none(self.params, 'koffee_filters'):
      self._form_ctpv2_filters(self.request.koffee_filters, json.loads(self.params['koffee_filters']))

  def _form_ctpv2_suite_request(self):
    """Fills in the ctpv2 field for suite_request."""
    suite_request = self.request.suite_request
    suite_request.test_suite.name = self.params['suite']
    include_tags = self.params.get('include_tags', None)
    exclude_tags = self.params.get('exclude_tags', None)
    include_names = self.params.get('inlcude_names', None)
    exclude_names = self.params.get('exclude_names', None)
    if include_tags or exclude_tags or include_names or exclude_names:
      tag_criteria = suite_request.test_suite.test_case_tag_criteria
      tag_criteria.tags.extend(buildbucket._get_test_tags(include_tags))
      tag_criteria.tag_excludes.extend(buildbucket._get_test_tags(exclude_tags))
      tag_criteria.test_names.extend(buildbucket._get_test_tags(include_names))
      tag_criteria.test_name_excludes.extend(buildbucket._get_test_tags(exclude_names))

  def _form_ctpv2_targets(self):
    """Parse out targets from params and create ctpv2 target objects.

    Use targets field for individual dut requests. Use schedule targets
    field for multi-dut requests.
    """
    if not _key_not_none(self.params, 'targets'):
      return
    targets = self.request.targets
    schedule_targets = self.request.schedule_targets
    for dut_targets in json.loads(self.params['targets']):
      if len(dut_targets) == 1:
        target_dict = dut_targets[0]
        target = targets.add()
        self._form_ctpv2_target(target, target_dict)
      else:
        schedule_target = schedule_targets.add()
        for dut_target in dut_targets:
          target = schedule_target.targets.add()
          self._form_ctpv2_target(target, dut_target)

  def _form_ctpv2_target(self, target, target_dict):
    """Fill in target fields from dictionary of values.

    Args:
      target: target proto object being filled.
      target_dict: dict containing target fields.
    """
    sw_targets = target.sw_targets
    sw_target = sw_targets.add()
    if _key_not_none(target_dict, 'board'):
      target.hw_target.legacy_hw.board = target_dict['board']
    if _key_not_none(target_dict, 'model'):
      target.hw_target.legacy_hw.model = target_dict['model']
    if _key_not_none(target_dict, 'variant'):
      sw_target.legacy_sw.variant = target_dict['variant']
    if _key_not_none(target_dict, 'build_type'):
      sw_target.legacy_sw.build = target_dict['build_type']
    if _key_not_none(target_dict, 'test_source_build'):
      sw_target.legacy_sw.gcs_path = buildbucket.get_gs_prefix(self.params) + target_dict['test_source_build']
      self.req_tags.append(bb_common_pb2.StringPair(
        key='label-image',
        value=target_dict['test_source_build'],
      ))

  def _form_ctpv2_filters(self, request_filters, k_filters):
    """Form the ctpv2 filters from provided filter dictionaries.

    Args:
      request_filters: proto object representing ctpv2 filter requests.
      k_filters: list of dictionaries of filter info.
    """
    for k_filter in k_filters:
      request_filter = request_filters.add()
      if _key_not_none(k_filter, 'container_metadata'):
        request_filter.container_metadata = _filter['container_metadata']
      if _key_not_none(k_filter, 'container'):
        container = request_filter.container
        self._form_container_image_info(container, k_filter['container'])
      if _key_not_none(k_filter, 'dependentContainers'):
        dependent_filters = request_filter.dependent_containers
        for image_info in k_filter['dependentContainers']:
          container = dependent_filters.add()
          self._form_container_image_info(container, image_info)

  def _form_container_image_info(self, container, image_info):
    """Form container image info for filters.

    Args:
      container: proto object representing container info.
      image_info: dictionary of image info.
    """
    if _key_not_none(image_info, 'repository'):
      repository = image_info['repository']
      if _key_not_none(repository, 'hostname'):
        container.repository.hostname = repository['hostname']
      if _key_not_none(repository, 'project'):
        container.repository.project = repository['project']
    if _key_not_none(image_info, 'name'):
      container.name = image_info['name']
    if _key_not_none(image_info, 'digest'):
      container.digest = image_info['digest']
    if _key_not_none(image_info, 'tags'):
      container.tags.extend(image_info['tags'])


def _key_not_none(_dict, key):
  """Check if key exists and dictionary and is not None.

  Args:
    _dict: dict.
    key: string.

  Returns:
    A boolean; true when dictionary containers key and key is not None.
  """
  return _dict.has_key(key) and _dict.get(key) not in ['None', None]
