# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for miscellanious helping functions for request building."""

def form_ctpv2_filters(request_filters, k_filters):
  """Form the ctpv2 filters from provided filter dictionaries.

  Args:
    request_filters: proto object representing ctpv2 filter requests.
    k_filters: list of dictionaries of filter info.
  """
  for k_filter in k_filters:
    request_filter = request_filters.add()
    if key_not_none(k_filter, 'containerMetadata'):
      request_filter.container_metadata = k_filter['containerMetadata']
    if key_not_none(k_filter, 'containerInfo'):
      container = request_filter.container_info
      form_container_info(container, k_filter['containerInfo'])
    if key_not_none(k_filter, 'dependentContainersInfo'):
      dependent_filters = request_filter.dependent_containers_info
      form_container_info(dependent_filters, k_filter['dependentContainersInfo'])


def form_container_info(container, container_info):
  """Form container info for filters.

  Args:
    container: proto object representing container info.
    container_info: dictionary of container info.
  """
  container.binary_name = container_info['binaryName']
  container.binary_args.extend(container_info['binaryArgs'])
  image_info = container.container
  if key_not_none(container_info, 'container'):
    form_container_image_info(image_info, container_info['container'])


def form_container_image_info(container, image_info):
  """Form container image info for filters.

  Args:
    container: proto object representing container info.
    image_info: dictionary of image info.
  """
  if key_not_none(image_info, 'repository'):
    repository = image_info['repository']
    if key_not_none(repository, 'hostname'):
      container.repository.hostname = repository['hostname']
    if key_not_none(repository, 'project'):
      container.repository.project = repository['project']
  if key_not_none(image_info, 'name'):
    container.name = image_info['name']
  if key_not_none(image_info, 'digest'):
    container.digest = image_info['digest']
  if key_not_none(image_info, 'tags'):
    container.tags.extend(image_info['tags'])


def key_not_none(_dict, key):
  """Check if key exists and dictionary and is not None.

  Args:
    _dict: dict.
    key: string.

  Returns:
    A boolean; true when dictionary containers key and key is not None.
  """
  return _dict.has_key(key) and _dict.get(key) not in ['None', None]
