# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for ChromeOS & Android build related logic in suite scheduler."""
# pylint: disable=g-bad-import-order

from distutils import version
import collections
import json
import logging
import re

import apiclient

BuildInfo = collections.namedtuple(
    'BuildInfo',
    [
        'board',
        'model',
        'milestone',
        'platform',
        'build_config',
    ])

# Bare branches
BARE_BRANCHES = ['factory', 'firmware']

# Definition of os types.
OS_TYPE_CROS = 'cros'
OS_TYPE_BRILLO = 'brillo'
OS_TYPE_ANDROID = 'android'
OS_TYPES = [OS_TYPE_CROS, OS_TYPE_BRILLO, OS_TYPE_ANDROID]
OS_TYPES_LAUNCH_CONTROL = [OS_TYPE_BRILLO, OS_TYPE_ANDROID]

# Launch control build's target's information
LaunchControlBuildTargetInfo = collections.namedtuple(
    'LaunchControlBuildTargetInfo',
    [
        'target',
        'type',
    ])

# ChromeOS build config's information
CrOSBuildConfigInfo = collections.namedtuple(
    'CrOSBuildConfigInfo',
    [
        'board',
        'type',
    ])

# The default build type for fetching latest build.
_DEFAULT_BUILD_SUFFIX = '-release'

# The default setting of board for fetching latest build.
_DEFAULT_HEAD = 'master'

# The path for storing the latest build.
_GS_LATEST_HEAD_PATTERN = '%(board)s%(suffix)s/%(name)s'

# The gs bucket to fetch the latest build.
_GS_BUCKET = 'chromeos-image-archive'

# The file in Google Storage to fetch the latest build.
_LATEST_HEAD = 'LATEST-main'

# The bucket for ChromeOS build release boards. Maintained by GoldenEye.
_GE_RELEASE_BUILD_BUCKET = 'chromeos-build-release-console'

# Special android target to board map.
_ANDROID_TARGET_TO_BOARD_MAP = {
    'seed_l8150': 'gm4g_sprout',
    'bat_land': 'bat'
}

# CrOS build name patter
_CROS_BUILD_PATTERN = '%(board)s-%(build_type)s/R%(milestone)s-%(manifest)s'

# Android build name pattern
_ANDROID_BUILD_PATTERN = '%(branch)s/%(target)s/%(build_id)s'

# The pattern for Launch Control target
_LAUNCH_CONTROL_TARGET_PATTERN = r'(?P<build_target>.+)-(?P<build_type>[^-]+)'

# The pattern for CrOS build config
_CROS_BUILD_CONFIG_PATTERN = r'-([^-]+)(?:-group)?'


class NoBuildError(Exception):
  """Raised when failing to get the required build from Google Storage."""


class BuildType(object):
  """Representing the type of test source build.

  This is used to identify the test source build for testing.
  """
  FIRMWARE_RW = 'firmware_rw'
  FIRMWARE_RO = 'firmware_ro'
  CROS = 'cros'


class BuildVersionKey(object):
  """Keys referring to the builds to install in run_suites."""

  CROS_VERSION = 'cros_version'
  ANDROID_BUILD_VERSION = 'android_version'
  TESTBED_BUILD_VERSION = 'testbed_version'
  FW_RW_VERSION = 'fwrw_version'
  FW_RO_VERSION = 'fwro_version'


class AndroidBuild(collections.namedtuple(
    '_AndroidBuildBase', ['branch', 'target', 'build_id']), object):
  """Class for constructing android build string."""

  def __str__(self):
    return _ANDROID_BUILD_PATTERN % {'branch': self.branch,
                                     'target': self.target,
                                     'build_id': self.build_id}


class CrOSBuild(collections.namedtuple(
    '_CrOSBuildBase',
    ['board', 'build_type', 'milestone', 'manifest']), object):
  """Class for constructing ChromeOS build string."""

  def __str__(self):
    return _CROS_BUILD_PATTERN % {'board': self.board,
                                  'build_type': self.build_type,
                                  'milestone': self.milestone,
                                  'manifest': self.manifest}


def get_latest_cros_build_from_gs(storage_client, board=None, suffix=None):
  """Get latest build for given board from Google Storage.

  Args:
    storage_client: a rest_client.StorageRestClient object.
    board: the board to fetch latest build. Default is 'master'.
    suffix: suffix represents build channel, like '-release'.
      Default is '-paladin'.

  Returns:
    a ChromeOS version string, e.g. '59.0.000.0'.

  Raises:
    HttpError if error happens in interacting with Google Storage.
  """
  board = board if board is not None else _DEFAULT_HEAD
  suffix = suffix if suffix is not None else _DEFAULT_BUILD_SUFFIX
  file_to_check = _GS_LATEST_HEAD_PATTERN % {
      'board': board,
      'suffix': suffix,
      'name': _LATEST_HEAD}

  try:
    return storage_client.read_object(_GS_BUCKET, file_to_check)
  except apiclient.errors.HttpError as e:
    raise NoBuildError(
        'Cannot find latest build for board %s, suffix %s: %s' %
        (board, suffix, str(e)))


def get_board_family_mapping_from_gs(storage_client):
  """Get board_family to boards mapping from Google Storage.

  Args:
    storage_client: a rest_client.StorageRestClient object.

  Returns:
    a dictionary of mapping between board family name to boards, e.g.
      {'nyan': ['nyan', 'nyan_big', 'nyan_blaze', ..]}

  Raises:
    HttpError if error happens in interacting with Google Storage.
  """
  try:
    boards = storage_client.read_object(_GE_RELEASE_BUILD_BUCKET, 'boards.json')
    json_object = json.loads(boards)
    board_family = {}
    for board in json_object['boards']:
      group = board['reference_group']
      if not group:
        continue

      # This is to change boards like nyan-blaze to nyan_blaze, which is
      # actually used in lab.
      board_name = board['public_codename'].replace('-', '_')
      if group not in board_family:
        board_family[group] = []

      board_family[group].append(board_name)

    logging.info('Successfully get following board families from GS: %r',
                 board_family.keys())
    return board_family
  except apiclient.errors.HttpError as e:
    logging.error('Cannot load boards.json in bucket %s: %s',
                  _GE_RELEASE_BUILD_BUCKET, str(e))
    raise


def buildinfo_list_to_branch_build_dict(cros_board_list, buildinfo_list,
                                        rubik_build_targets = None,
                                        use_rubik = False):
  """Validate and convert a list of BuildInfo to branch build dict.

  Args:
    cros_board_list: The board list including all CrOS boards.
    buildinfo_list: A list of BuildInfo objects.
    rubik_build_targets: A set of build targets to use Rubik builds for.
    use_rubik: bool. If True will only keep builds for build targets in
      rubik_build_targets. If False, will only keep build targets not in
      rubik_build_targets.

  Returns:
    A branch build dict:
        key: a tuple of (board, build_type, milestone), like:
          ('wolf', 'release', '58')
        value: the latest manifest for the given tuple, like:
          '9242.0.0'.
  """
  branch_build_dict = {}
  for build in buildinfo_list:
    try:
      build_config_info = parse_cros_build_config(build.board,
                                                  build.build_config)
    except ValueError as e:
      logging.warning('Failed to parse build config: %s: %s',
                      build.build_config, e)
      continue

    if build.board != build_config_info.board:
      logging.warning('Non-matched build_config and board: %s, %s',
                      build.board, build.board)
      continue

    if build.board not in cros_board_list:
      logging.warning('%s is not a valid CrOS board.', build.board)
      continue

    if rubik_build_targets:
      if use_rubik:
        # Discard builds for build targets not in rubik_build_targets.
        if build.board not in rubik_build_targets:
          logging.warning('%s is not a Rubik board, discarding.', build.board)
          continue
      else:
        # Discard builds for build targets in rubik_build_targets.
        if build.board in rubik_build_targets:
          logging.warning('%s is a Rubik board, discarding.', build.board)
          continue

    build_key = (build.board, build.model, build_config_info.type,
                 build.milestone)
    cur_manifest = branch_build_dict.get(build_key)
    if cur_manifest is not None:
      branch_build_dict[build_key] = max(
          [cur_manifest, build.platform], key=version.LooseVersion)
    else:
      branch_build_dict[build_key] = build.platform

  return branch_build_dict


def get_cros_builds(build_client, cros_board_list, earliest_end_time,
                    latest_end_time, event_type, rubik_build_targets = None):
  """Get branch builds for ChromeOS boards inside the given time span.

  Args:
    build_client: a rest_client.BuildBucketBigqueryClient object, to
      connect Buildbucket Bigquery.
    cros_board_list: The board list including all CrOS boards.
    earliest_end_time: a datetime.datetime object in UTC.
    latest_end_time: a datetime.datetime object in UTC.
    event: a string of event type.
    rubik_build_targets: set of build targets for which we should use Rubik
      builds instead of Leagcy.

  Returns:
    a two-tuple of branch build dicts.  Each branch build dict has
    keys and value described below.  The first build_dict describes
    successful builds and the second describes builds that failed
    but met the relaxed success requirement (a successful 'UploadTestArtifacts'
    stage).
        key: a tuple of (board, build_type, milestone), like:
          ('wolf', 'release', '58')
        value: the latest manifest for the given tuple, like:
          '9242.0.0'.
  """
  # Buildbucket Bigquery use UTC timezone
  all_branch_builds = build_client.get_passed_builds(
      earliest_end_time, latest_end_time, event_type)
  relaxed_builds = build_client.get_relaxed_passed_builds(
      earliest_end_time, latest_end_time, event_type)
  all_branch_rubik_builds = build_client.get_passed_rubik_builds(
      earliest_end_time, latest_end_time, event_type)

  # TODO(b/225382624): Remove all logic fetching Legacy builds
  branch_builds_dict = buildinfo_list_to_branch_build_dict(
      cros_board_list, all_branch_builds, rubik_build_targets=rubik_build_targets)
  rubik_branch_builds_dict = buildinfo_list_to_branch_build_dict(
      cros_board_list, all_branch_rubik_builds, rubik_build_targets=rubik_build_targets,
      use_rubik=True)
  relaxed_builds_dict = buildinfo_list_to_branch_build_dict(
      cros_board_list, relaxed_builds + all_branch_builds,
      rubik_build_targets=rubik_build_targets)
  # Include Rubik builds in the relaxed builds dict. We can't pass the rubik
  # builds to the above call because they'll get filtered out (use_rubik is False).
  relaxed_builds_dict.update(rubik_branch_builds_dict)

  return dict(branch_builds_dict, **rubik_branch_builds_dict), relaxed_builds_dict


def get_latest_launch_control_build(android_client, branch, target):
  """Get the latest launch control build from Android Build API.

  Args:
    android_client: a rest_client.AndroidBuildRestClient object.
    branch: the launch control branch.
    target: the launch control target.

  Returns:
    a string latest launch control build id.

  Raises:
    NoBuildError if no latest launch control build is found.
  """
  try:
    latest_build_id = android_client.get_latest_build_id(branch, target)
    if latest_build_id is None:
      raise NoBuildError('No latest builds is found.')

    return latest_build_id
  except apiclient.errors.HttpError as e:
    raise NoBuildError('HttpError happened in getting the latest launch '
                       'control build for '
                       '%s,%s: %s' % (branch, target, str(e)))


def get_launch_control_builds_by_branch_targets(
    android_client, android_board_list, launch_control_branch_targets):
  """Get latest launch_control_builds for android boards.

  For every tasks in this event, if it has settings of launch control
  branch & target, get the latest launch control build for it.

  Args:
    android_client: a rest_client.AndroidBuildRestClient object to
      interact with android build API.
    android_board_list: a list of Android boards.
    launch_control_branch_targets: a dict of branch:targets, see property
      launch_control_branch_targets in base_event.py.

  Returns:
    a launch control build dict:
      key: an android board, like 'shamu'.
      value: a list involves the latest builds for each pair
        (branch, target) of this board, like:
            [u'git_nyc-mr2-release/shamu-userdebug/3844975',
             u'git_nyc-mr1-release/shamu-userdebug/3783920']
  """
  launch_control_dict = {}
  board_to_builds_dict = {}
  for branch, targets in launch_control_branch_targets.iteritems():
    for t in targets:
      try:
        board = parse_launch_control_target(t).target
      except ValueError:
        logging.warning(
            'Failed to parse launch control target: %s', t)
        continue

      if board not in android_board_list:
        continue

      # Use dict here to reduce the times to call AndroidBuild API
      if launch_control_dict.get((branch, t)) is None:
        try:
          build_id = get_latest_launch_control_build(
              android_client, branch, t)
        except NoBuildError as e:
          logging.warning(e)
          continue

        build = str(AndroidBuild(branch, t, build_id))
        launch_control_dict[(branch, t)] = build
        board_to_builds_dict.setdefault(board, []).append(
            build)

  for board, in board_to_builds_dict.iteritems():
    mapped_board = get_board_by_android_target(board)
    if mapped_board != board:
      logging.debug('Map board %s to %s', board, mapped_board)
      if board_to_builds_dict.get(mapped_board) is None:
        del board_to_builds_dict[board]
      else:
        board_to_builds_dict[board] = board_to_builds_dict[
            mapped_board]

  return board_to_builds_dict


def parse_launch_control_target(target):
  """Parse the build target and type from a Launch Control target.

  The Launch Control target has the format of build_target-build_type, e.g.,
  shamu-eng or dragonboard-userdebug. This method extracts the build target
  and type from the target name.

  Args:
    target: Name of a Launch Control target, e.g., shamu-userdebug.

  Returns:
    a LaunchControlBuildTargetInfo object whose value is like
        (target='shamu',
         type='userdebug')

  Raises:
    ValueError: if target is not valid.
  """
  match = re.match(_LAUNCH_CONTROL_TARGET_PATTERN, target)
  if not match:
    raise ValueError('target format is not valid')

  return LaunchControlBuildTargetInfo(match.group('build_target'),
                                      match.group('build_type'))


def parse_cros_build_config(board, build_config):
  """Parse build_type from a given builder for a given board.

  Args:
    board: the prefix of a ChromeOS build_config, representing board.
    build_config: a ChromeOS build_config name, like 'kevin-release'.

  Returns:
    a CrOSBuildConfigInfo object whose value is like
        (board='kevin',
         type='release')

  Raises:
    ValueError: if build_config is in invalid form.
  """
  if build_config[0:len(board)] != board:
    raise ValueError('build_config cannot be parsed: %s' % build_config)

  match = re.match(_CROS_BUILD_CONFIG_PATTERN, build_config[len(board):])
  if not match:
    raise ValueError('build_config %s is not matched %s' % (
        build_config, _CROS_BUILD_CONFIG_PATTERN))

  return CrOSBuildConfigInfo(board, match.groups()[0])


def get_board_by_android_target(target):
  """Map a android target to a android board.

  # Mapping between an android board name and a build target. This is for
  # special case handling for certain Android board that the board name and
  # build target name does not match.
  # This comes from server/site_utils.py in autotest module.

  Args:
    target: an android target.

  Returns:
    a string android board mapped by ANDROID_TARGET_TO_BOARD_MAP.
  """
  return _ANDROID_TARGET_TO_BOARD_MAP.get(target, target)


def to_full_model(board, model):
  """Form a full model name with given board, model.

  Args:
    board: A string board name.
    model: A string model name.

  Returns:
    A string full_model name.
  """
  return '%s_%s' % (board, model)


def reshape_board(board):
  """Reshape some variants of board names to original board.

  Args:
    board: A string board name.

  Returns:
    A string board name after reshaping.
  """
  # The hack derives from build info structure saved in CIDB/buildbucket:
  # *-kernelnext/*-arcnext etc are saved as board name, but not the real board
  # for DUT.
  # NOTE: please try to keep this list in sync with the corresponding list in
  # chromite/lib/config_lib.py
  special_suffixes = [
    '-arc64', #
    '-arc-r', #
    '-arc-r-userdebug', #
    '-arc-s', #
    '-arcnext', #
    '-arcvm', #
    '-connectivitynext', #
    '-borealis', #
    '-campfire', #
    '-cfm', #
    '-kernelnext', #
    '-kvm', #
    '-libcamera', #
    '-manatee', #
    '-ndktranslation', #
    '-userdebug', #
  ]
  # ARM64 userspace boards use 64 suffix but can't put that in list above
  # because of collisions with boards like kevin-arc64.
  ARM64_BOARDS = ['kevin64', 'trogdor64']
  for s in special_suffixes:
    if board.endswith(s):
      board = board[:-len(s)]
  if board in ARM64_BOARDS:
    # Remove '64' suffix from the board name.
    board = board[:-2]
  return board
