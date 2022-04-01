# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for build_lib unittests."""

import unittest

import build_lib


class FakeBuildClient(object):
  """Mock rest_client.BuildBucketBigqueryClient."""

  def __init__(self):
    self.firmware_builds_called = 0

  def get_passed_builds(self, earliest, latest, event_type):
    """Mock get_passed_builds."""
    del earliest  # unused
    del latest # unused
    del event_type  #unused
    return [
        build_lib.BuildInfo(
            'link', None, '62', '9868.0.0', 'link-release'),
        build_lib.BuildInfo(
            'zako', None, '62', '9868.0.0', 'zako-release'),
        build_lib.BuildInfo('samus-kernelnext', None, '62',
                            '9868.0.0', 'samus-kernelnext-release'),
        build_lib.BuildInfo(
            'reef', None, '62', '1234.0.0', 'reef-release'),
        build_lib.BuildInfo(
            'coral', 'santa', '62', '9868.0.0', 'coral-release'),
        build_lib.BuildInfo(
            'coral', 'astronaut', '62', '9868.0.0', 'coral-release'),
        build_lib.BuildInfo(
            'coral', 'lava', '62', '9868.0.0', 'coral-release'),
        build_lib.BuildInfo(
            'atlas-kernelnext', None, '62', '9868.0.0', 'atlas-kernelnext-release'),
    ]

  def get_passed_rubik_builds(self, earliest, latest, event_type):
    """Mock get_passed_rubik_builds."""
    del earliest  # unused
    del latest # unused
    del event_type  #unused
    return [
        build_lib.BuildInfo(
            'atlas-kernelnext', None, '62', '9869.0.0', 'atlas-kernelnext-release'),
        build_lib.BuildInfo(
            'coral', 'lava', '62', '9869.0.0', 'coral-release'),
    ]

  def get_relaxed_passed_builds(self, earliest, latest, event_type):
    """Mock get_relaxed_pased_builds."""
    del earliest  # unused
    del latest # unused
    del event_type  #unused
    return []


class BuildLibTestCase(unittest.TestCase):

  def testReshapeBoard(self):
    self.assertEqual(build_lib.reshape_board('samus-kernelnext'), 'samus')
    self.assertEqual(build_lib.reshape_board('eve-arcvm'), 'eve')
    self.assertEqual(build_lib.reshape_board('kukui-arc-r'), 'kukui')
    self.assertEqual(build_lib.reshape_board('hatch-arc-r-userdebug'), 'hatch')
    self.assertEqual(build_lib.reshape_board('hatch-arc-s'), 'hatch'),
    self.assertEqual(build_lib.reshape_board('kevin-userdebug'), 'kevin')
    self.assertEqual(build_lib.reshape_board('octopus'), 'octopus')
    self.assertEqual(build_lib.reshape_board('hana-arc64'), 'hana')

  def testGetCrosBuilds(self):
    mock_build_client = FakeBuildClient()
    cros_board_list = ['coral', 'atlas-kernelnext']
    rubik_build_targets = ['atlas-kernelnext']
    build_dict, relaxed_build_dict = build_lib.get_cros_builds(
      mock_build_client, cros_board_list, None, None, None,
      rubik_build_targets=rubik_build_targets)

    expected_build_dict = {
      ('coral', 'santa', 'release', '62'): '9868.0.0',
      ('coral', 'astronaut', 'release', '62'): '9868.0.0',
      ('coral', 'lava', 'release', '62'): '9868.0.0',
      ('atlas-kernelnext', None, 'release', '62'): '9869.0.0'
    }
    self.assertEqual(expected_build_dict, build_dict)
    self.assertEqual(expected_build_dict, relaxed_build_dict)


if __name__ == '__main__':
  unittest.main()
