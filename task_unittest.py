# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for task unittests."""
# pylint: disable=g-missing-super-call

import re
import unittest

import build_lib
import config_reader
import mock
import task
import task_config_reader
import tot_manager


class FakeTotMilestoneManager(tot_manager.TotMilestoneManager):
  """Mock class for tot_manager.TotMilestoneManager."""

  def __init__(self, is_sanity):
    self.is_sanity = is_sanity
    self.storage_client = None
    self.tot = self._tot_milestone()


class FakeBuildClient(object):
  """Mock rest_client.BuildBucketBigqueryClient."""

  def __init__(self, success=True):
    self.success = success

  def get_latest_passed_builds(self, build_config):
    if not self.success:
      raise ValueError('No valid builds')

    return build_lib.BuildInfo(board=build_config.split('-')[0],
                               model=None,
                               milestone=TaskTestCase.MILESTONE,
                               platform=TaskTestCase.PLATFORM,
                               build_config=build_config)


class FakeLabConfig(object):
  """Mock class for config_reader.LabConfig."""

  def get_cros_model_map(self):
    return {'coral': ['robo', 'nasher', 'lava']}


class FakeMigrationConfig(object):
  """Mock class for config_reader.MigrationConfig."""

  def get_skylab_suites_dump(self):
    return {}


class TaskBaseTestCase(unittest.TestCase):

  BOARD = 'fake_board'
  UNIBUILD_BOARD = 'coral'
  EXCLUDE_BOARD = 'exclude_fake_board'
  NAME = 'fake_name'
  SUITE = 'fake_suite'
  POOL = 'fake_pool'
  PLATFORM = '6182.0.0-rc2'
  MILESTONE = '30'
  NUM = 1
  PRIORITY = 50
  TIMEOUT = 600

  def setUp(self):
    tot_patcher = mock.patch('tot_manager.TotMilestoneManager')
    self._mock_tot = tot_patcher.start()
    self.addCleanup(tot_patcher.stop)
    # Can't pass in False since storage_client is not mocked.
    self._mock_tot.return_value = FakeTotMilestoneManager(True)
    self.task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=[],
        pool=self.POOL,
        num=self.NUM,
        boards=','.join([self.BOARD, self.UNIBUILD_BOARD]),
        exclude_boards=self.EXCLUDE_BOARD,
        priority=self.PRIORITY,
        timeout=self.TIMEOUT))

    self._empty_configs = config_reader.Configs(
        lab_config=config_reader.LabConfig(None),
        migration_config=config_reader.MigrationConfig(None))
    self._fake_configs = config_reader.Configs(
        lab_config=FakeLabConfig(),
        migration_config=FakeMigrationConfig())


class TaskTestCase(TaskBaseTestCase):

  def setUp(self):
    super(TaskTestCase, self).setUp()

    mock_push = mock.patch('task.Task._push_suite')
    self._mock_push = mock_push.start()
    self.addCleanup(mock_push.stop)

  def testSetSpecCompareInfoEqual(self):
    """Test compare info setting for specs that equals to a milestone."""
    self.task.branch_specs = re.split(r'\s*,\s*', '==tot-2')
    self.task._set_spec_compare_info()
    self.assertTrue(self.task._version_equal_constraint)
    self.assertFalse(self.task._version_gte_constraint)
    self.assertFalse(self.task._version_lte_constraint)
    self.assertEqual(self.task._bare_branches, [])

  def testSetSpecCompareInfoLess(self):
    """Test compare info setting for specs that is less than a milestone."""
    self.task.branch_specs = re.split(r'\s*,\s*', '<=tot')
    self.task._set_spec_compare_info()
    self.assertFalse(self.task._version_equal_constraint)
    self.assertFalse(self.task._version_gte_constraint)
    self.assertTrue(self.task._version_lte_constraint)
    self.assertEqual(self.task._bare_branches, [])

  def testSetSpecCompareInfoGreater(self):
    """Test compare info setting for specs that is greater than a milestone."""
    self.task.branch_specs = re.split(r'\s*,\s*', '>=tot-2')
    self.task._set_spec_compare_info()
    self.assertFalse(self.task._version_equal_constraint)
    self.assertTrue(self.task._version_gte_constraint)
    self.assertFalse(self.task._version_lte_constraint)
    self.assertEqual(self.task._bare_branches, [])

  def testFitsSpecEqual(self):
    """Test milestone check for specs that equals to a milestone."""
    self.task.branch_specs = re.split(r'\s*,\s*', '==tot-1')
    self.task._set_spec_compare_info()
    self.assertFalse(self.task._fits_spec('40'))
    self.assertTrue(self.task._fits_spec('39'))
    self.assertFalse(self.task._fits_spec('38'))

  def testFitsSpecLess(self):
    """Test milestone check for specs that is less than a milestone."""
    self.task.branch_specs = re.split(r'\s*,\s*', '<=tot-1')
    self.task._set_spec_compare_info()
    self.assertFalse(self.task._fits_spec('40'))
    self.assertTrue(self.task._fits_spec('39'))
    self.assertTrue(self.task._fits_spec('38'))

  def testFitsSpecGreater(self):
    """Test milestone check for specs that is greater than a milestone."""
    self.task.branch_specs = re.split(r'\s*,\s*', '>=tot-2')
    self.task._set_spec_compare_info()
    self.assertTrue(self.task._fits_spec('39'))
    self.assertTrue(self.task._fits_spec('38'))
    self.assertFalse(self.task._fits_spec('37'))

  def testGetFirmwareFromLabConfig(self):
    """Test get firmware from lab config successfully."""
    with mock.patch('config_reader.LabConfig.get_firmware_ro_build_list',
                    return_value='build1,build2'):
      firmware = self.task._get_firmware_build(
          'released_ro_2', self.BOARD, config_reader.LabConfig(None), None)
      self.assertEqual(firmware, 'build2')

  def testGetFirmwareFromLabConfigOutofIndex(self):
    """Test get firmware from lab config when firmware index is invalid."""
    with mock.patch('config_reader.LabConfig.get_firmware_ro_build_list',
                    return_value='build1,build2'):
      self.assertRaises(ValueError,
                        self.task._get_latest_firmware_build_from_lab_config,
                        'released_ro_3',
                        self.BOARD,
                        config_reader.LabConfig(None))
      self.assertIsNone(self.task._get_firmware_build(
          'released_ro_3', self.BOARD, config_reader.LabConfig(None), None))

  def testGetFirmwareFromDB(self):
    """Test get firmware from DB successfully."""
    firmware = self.task._get_firmware_build(
        'firmware', self.BOARD, None, FakeBuildClient())
    self.assertEqual(
        firmware,
        '%s-firmware/R%s-%s' % (self.BOARD, self.MILESTONE, self.PLATFORM))

  def testScheduleCrosSuccessfully(self):
    """test schedule cros builds successfully."""
    branch_builds = {(self.BOARD, None, 'release', '56'): '0000.00.00'}
    self.task._schedule_cros_builds(branch_builds,
                                    self._fake_configs,
                                    FakeBuildClient())
    self.assertEqual(self._mock_push.call_count, 1)

  def testScheduleCrosNonvalidBoard(self):
    """Test schedule no cros builds due to non-allowed board."""
    branch_builds = {('%s_2' % self.BOARD, None, 'release', '56'): '0000.00.00'}
    self.task._schedule_cros_builds(branch_builds,
                                    self._empty_configs,
                                    FakeBuildClient())
    self.assertEqual(self._mock_push.call_count, 0)

  def testScheduleCrosExcludeBoard(self):
    """Test schedule no cros builds due to board is excluded."""
    branch_builds = {(self.EXCLUDE_BOARD, None, 'release', '56'): '0000.00.00'}
    self.task._schedule_cros_builds(branch_builds,
                                    self._empty_configs,
                                    FakeBuildClient())
    self.assertEqual(self._mock_push.call_count, 0)

  def testScheduleCrosSuccessfullyWithSpecifiedModel(self):
    """Test schedule unibuild with specific model."""
    self.task.board = self.UNIBUILD_BOARD
    branch_builds = {(self.UNIBUILD_BOARD, 'robo', 'release', '56'):
                     '0000.00.00',
                     (self.UNIBUILD_BOARD, 'lava', 'release', '56'):
                     '0000.00.00'}
    self.task._schedule_cros_builds(branch_builds,
                                    self._fake_configs,
                                    FakeBuildClient())
    self.assertEqual(self._mock_push.call_count, 2)

  def testScheduleCrosNonValidSpec(self):
    """Test schedule no cros builds due to non-allowed branch milestone."""
    branch_builds = {(self.BOARD, None, 'release', '56'): '0000.00.00'}
    # Only run tasks whose milestone = tot (R40)
    self.task.branch_specs = re.split(r'\s*,\s*', '==tot')
    self.task._set_spec_compare_info()
    self.task._schedule_cros_builds(branch_builds,
                                    self._empty_configs,
                                    FakeBuildClient())
    self.assertEqual(self._mock_push.call_count, 0)

  def testScheduleCrosSuccessfullyWithValidFirmware(self):
    """Test schedule cros builds successfully with valid firmware."""
    branch_builds = {(self.BOARD, None, 'release', '56'): '0000.00.00'}
    self.task.firmware_ro_build_spec = 'firmware'
    self.task._schedule_cros_builds(branch_builds,
                                    self._fake_configs,
                                    FakeBuildClient())
    self.assertEqual(self._mock_push.call_count, 1)

  def testScheduleCrosWithNonValidFirmware(self):
    """Test schedule no cros builds due to non-existent firmware."""
    branch_builds = {(self.BOARD, None, 'release', '56'): '0000.00.00'}
    self.task.firmware_ro_build_spec = 'firmware'
    self.task._schedule_cros_builds(branch_builds,
                                    self._empty_configs,
                                    FakeBuildClient(success=False))
    self.assertEqual(self._mock_push.call_count, 0)

  def testScheduleLaunchControlWithFullBranches(self):
    """Test schedule all launch control builds successfully."""
    lc_builds = {self.BOARD: ['git_nyc-mr2-release/shamu-userdebug/3844975',
                              'git_nyc-mr1-release/shamu-userdebug/3783920']}
    lc_branches = 'git_nyc-mr1-release,git_nyc-mr2-release'
    self.task.launch_control_branches = [
        t.lstrip() for t in lc_branches.split(',')]
    self.task._schedule_launch_control_builds(lc_builds)
    self.assertEqual(self._mock_push.call_count, 2)

  def testScheduleLaunchControlWithPartlyBranches(self):
    """Test schedule part of launch control builds due to branch check."""
    lc_builds = {self.BOARD: ['git_nyc-mr2-release/shamu-userdebug/3844975',
                              'git_nyc-mr1-release/shamu-userdebug/3783920']}
    lc_branches = 'git_nyc-mr1-release'
    self.task.launch_control_branches = [
        t.lstrip() for t in lc_branches.split(',')]
    self.task._schedule_launch_control_builds(lc_builds)
    self.assertEqual(self._mock_push.call_count, 1)

  def testScheduleLaunchControlWithNoBranches(self):
    """Test schedule none of launch control builds due to branch check."""
    lc_builds = {self.BOARD: ['git_nyc-mr2-release/shamu-userdebug/3844975',
                              'git_nyc-mr1-release/shamu-userdebug/3783920']}
    self.task.launch_control_branches = []
    self.task._schedule_launch_control_builds(lc_builds)
    self.assertEqual(self._mock_push.call_count, 0)

  def testScheduleLaunchControlNonvalidBoard(self):
    """Test schedule none of launch control builds due to board check."""
    lc_builds = {'%s_2' % self.BOARD:
                 ['git_nyc-mr2-release/shamu-userdebug/3844975',
                  'git_nyc-mr1-release/shamu-userdebug/3783920']}
    lc_branches = 'git_nyc-mr1-release,git_nyc-mr2-release'
    self.task.launch_control_branches = [
        t.lstrip() for t in lc_branches.split(',')]
    self.task._schedule_launch_control_builds(lc_builds)
    self.assertEqual(self._mock_push.call_count, 0)

  def testScheduleLaunchControlExcludeBoard(self):
    """Test schedule none of launch control builds due to board check."""
    lc_builds = {self.EXCLUDE_BOARD:
                 ['git_nyc-mr2-release/shamu-userdebug/3844975',
                  'git_nyc-mr1-release/shamu-userdebug/3783920']}
    lc_branches = 'git_nyc-mr1-release,git_nyc-mr2-release'
    self.task.launch_control_branches = [
        t.lstrip() for t in lc_branches.split(',')]
    self.task._schedule_launch_control_builds(lc_builds)
    self.assertEqual(self._mock_push.call_count, 0)


class TaskPushTestCase(TaskBaseTestCase):

  def setUp(self):
    super(TaskPushTestCase, self).setUp()
    mock_push = mock.patch('task_executor.push')
    self._mock_push = mock_push.start()
    self.addCleanup(mock_push.stop)

  def testScheduleCrOSIsPushSuccessfully(self):
    """Test IS_PUSHED is changed if some CrOS suites are scheduled."""
    branch_builds = {(self.BOARD, None, 'release', '56'): '0000.00.00'}
    self.task.os_type = build_lib.OS_TYPE_CROS
    self.assertTrue(self.task.schedule(
        [], (branch_builds, []), self._fake_configs,
        FakeBuildClient()))

  def testScheduleLaunchControlIsPushSuccessfully(self):
    """Test IS_PUSHED is changed if some launch control suites are scheduled."""
    lc_builds = {self.BOARD: ['git_nyc-mr2-release/shamu-userdebug/3844975',
                              'git_nyc-mr1-release/shamu-userdebug/3783920']}
    lc_branches = 'git_nyc-mr1-release,git_nyc-mr2-release'
    self.task.launch_control_branches = [
        t.lstrip() for t in lc_branches.split(',')]
    self.task.os_type = build_lib.OS_TYPES_LAUNCH_CONTROL
    self.assertTrue(self.task.schedule(
        lc_builds, ([], []), self._empty_configs, FakeBuildClient()))

  def testScheduleCrosIsPushInvalidBoard(self):
    """Test schedule no cros builds due to non-allowed board."""
    branch_builds = (
        {('%s_2' % self.BOARD, None, 'release', '56'): '0000.00.00'}, {},
    )
    self.task.os_type = build_lib.OS_TYPE_CROS
    self.assertFalse(self.task.schedule(
        [], branch_builds, self._empty_configs, FakeBuildClient()))

  def testScheduleLaunchControlIsPushInvalidBoard(self):
    """Test schedule none of launch control builds due to board check."""
    lc_builds = {'%s_2' % self.BOARD:
                 ['git_nyc-mr2-release/shamu-userdebug/3844975',
                  'git_nyc-mr1-release/shamu-userdebug/3783920']}
    lc_branches = 'git_nyc-mr1-release,git_nyc-mr2-release'
    self.task.launch_control_branches = [
        t.lstrip() for t in lc_branches.split(',')]
    self.task.os_type = build_lib.OS_TYPES_LAUNCH_CONTROL
    self.task._schedule_launch_control_builds(lc_builds)
    self.assertFalse(self.task.schedule(
        lc_builds, ([], []), self._empty_configs, FakeBuildClient()))
