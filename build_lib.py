# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for ChromeOS & Android build related logic in suite scheduler."""

import apiclient
import collections
import logging
import re

# Bare branches
BARE_BRANCHES = ['factory', 'firmware']

# Definition of os types.
OS_TYPE_CROS = 'cros'
OS_TYPE_BRILLO = 'brillo'
OS_TYPE_ANDROID = 'android'
OS_TYPES = [OS_TYPE_CROS, OS_TYPE_BRILLO, OS_TYPE_ANDROID]
OS_TYPES_LAUNCH_CONTROL = [OS_TYPE_BRILLO, OS_TYPE_ANDROID]


LaunchControlBuildTargetInfo = collections.namedtuple(
    'LaunchControlBuildTargetInfo',
    [
      'target',
      'type',
    ])

CrOSBuildConfigInfo = collections.namedtuple(
    'CrOSBuildConfigInfo',
    [
      'board',
      'type',
    ])


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

    def __str__(self):
        return _ANDROID_BUILD_PATTERN % {'branch': self.branch,
                                         'target': self.target,
                                         'build_id': self.build_id}


class CrOSBuild(collections.namedtuple(
    '_CrOSBuildBase',
    ['board', 'build_type', 'milestone', 'manifest']), object):

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
    board = board if board is not None else _DEFAULT_MASTER
    suffix = suffix if suffix is not None else _DEFAULT_BUILD_SUFFIX
    file_to_check = _GS_LATEST_MASTER_PATTERN % {
        'board': board,
        'suffix': suffix,
        'name': _LATEST_MASTER}

    try:
        return storage_client.ReadObject(_GS_BUCKET, file_to_check)
    except apiclient.errors.HttpError as e:
        raise NoBuildError(
            'Cannot find latest build for board %s, suffix %s: %s' %
            (board, suffix, str(e)))


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
        Raise ValueError if target is not valid.
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
        Raise ValueError if target is not valid.
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
        board: an android board.

    Returns:
        a string android board mapped by ANDROID_TARGET_TO_BOARD_MAP.
    """
    return _ANDROID_TARGET_TO_BOARD_MAP.get(target, target)


# The default build type for fetching latest build.
_DEFAULT_BUILD_SUFFIX = '-paladin'

# The default setting of board for fetching latest build.
_DEFAULT_MASTER = 'master'

# The path for storing the latest build.
_GS_LATEST_MASTER_PATTERN = '%(board)s%(suffix)s/%(name)s'

# The gs bucket to fetch the latest build.
_GS_BUCKET = 'chromeos-image-archive'

# The file in Google Storage to fetch the latest build.
_LATEST_MASTER = 'LATEST-master'

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
