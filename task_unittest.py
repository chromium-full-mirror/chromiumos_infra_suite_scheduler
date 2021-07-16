# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for task unittests."""
# pylint: disable=g-missing-super-call

import json
import re
import unittest

import build_lib
import config_reader
import mock
import task
import task_config_reader
import tot_manager

from chromite.api.gen.test_platform.suite_scheduler import analytics_pb2
from chromite.api.gen.chromiumos import branch_pb2

from chromite.third_party.google.protobuf import json_format

FAKE_UUID = 'c78e0bf3-4142-11ea-bc66-88e9fe4c5349'


class FakeTotMilestoneManager(tot_manager.TotMilestoneManager):
  """Mock class for tot_manager.TotMilestoneManager."""

  def __init__(self, is_sanity):
    self.is_sanity = is_sanity
    self.storage_client = None
    self.tot = self._tot_milestone()


class FakeLabConfig(object):
  """Mock class for config_reader.LabConfig."""

  def get_cros_model_map(self):
    return {'coral': ['robo', 'nasher', 'lava'], 'hatch': ['akemi', 'kled']}


class FakeBigqueryRestClient(object):

  def __init__(self, rest_client, project=None, dataset=None, table=None):
    """Initialize the mock class."""
    self.table = table
    self.rows = []

  def insert(self, rows):
    self.rows = rows
    return True


class TaskBaseTestCase(unittest.TestCase):

  BOARD = 'fake_board'
  UNIBUILD_BOARD = 'coral'
  EXCLUDE_BOARD = 'exclude_fake_board'
  NAME = 'fake_name'
  ANALYTICS_NAME='fake_name'
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

    _mock_bq_client = mock.patch('rest_client.BigqueryRestClient')
    mock_bq_client = _mock_bq_client.start()
    self.addCleanup(_mock_bq_client.stop)
    self.mock_bq_client = FakeBigqueryRestClient(
        None, project='proj', dataset='dataset', table='foo')
    mock_bq_client.return_value = self.mock_bq_client

    self.task = task.Task(
        task_config_reader.TaskInfo(
            name=self.NAME,
            suite=self.SUITE,
            branch_specs=[],
            analytics_name=self.ANALYTICS_NAME,
            pool=self.POOL,
            num=self.NUM,
            boards=','.join(
                [self.BOARD, self.UNIBUILD_BOARD]),
            exclude_boards=self.EXCLUDE_BOARD,
            priority=self.PRIORITY,
            timeout=self.TIMEOUT))

    self._empty_configs = config_reader.Configs(
      lab_config=config_reader.LabConfig(None))
    self._fake_configs = config_reader.Configs(
        lab_config=FakeLabConfig())

    self.firmware_dict = {
        ('cros', 'fake_board'): ('fake_board-release/R30-6182.0.0-rc2'),
        ('firmware', 'fake_board'): ('firmware-fake_board-12345.67.'
                                     'A-firmwarebranch/RFoo-1.0.0-b1234567'
                                     '/fake_board')
      }


class TaskTestCase(TaskBaseTestCase):

  def setUp(self):
    super(TaskTestCase, self).setUp()

    mock_push = mock.patch('task.Task._push_suite')
    self._mock_push = mock_push.start()
    self.addCleanup(mock_push.stop)

  def tearDown(self):
    self.task.boards = ','.join([self.BOARD, self.UNIBUILD_BOARD])
    self.task.models = None

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

  def testGetFirmwareSuccessfully(self):
    """Test get firmware from firmware_dict successfully."""

    firmware = self.task._get_firmware_build(
        'cros', self.BOARD, self.firmware_dict, None)
    self.assertEqual(
        firmware,
        '{0}-release/R{1}-{2}'.format(self.BOARD,
                                      self.MILESTONE,
                                      self.PLATFORM))
    firmware = self.task._get_firmware_build(
        'firmware', self.BOARD, self.firmware_dict, None)
    self.assertEqual(
        firmware,
        'firmware-{0}-12345.67.A-firmwarebranch/'
        'RFoo-1.0.0-b1234567/{0}'.format(self.BOARD))

  def testGetNonExistentBoard(self):
    """Test get firmware for non-existent board from firmware_dict."""
    self.assertIsNone(self.task._get_firmware_build(
        'firmware', 'non-existent', self.firmware_dict, None))

  def testScheduleCrosSuccessfully(self):
    """test schedule cros builds successfully."""
    branch_builds = {(self.BOARD, None, 'release', '56'): '0000.00.00'}
    self.task._schedule_cros_builds(branch_builds,
                                    self.firmware_dict,
                                    self._fake_configs)
    self.assertEqual(self._mock_push.call_count, 1)

  def testScheduleCrosNonvalidBoard(self):
    """Test schedule no cros builds due to non-allowed board."""
    branch_builds = {('%s_2' % self.BOARD, None, 'release', '56'): '0000.00.00'}
    self.task._schedule_cros_builds(branch_builds,
                                    self.firmware_dict,
                                    self._empty_configs)
    self.assertEqual(self._mock_push.call_count, 0)

  def testScheduleCrosExcludeBoard(self):
    """Test schedule no cros builds due to board is excluded."""
    branch_builds = {(self.EXCLUDE_BOARD, None, 'release', '56'): '0000.00.00'}
    self.task._schedule_cros_builds(branch_builds,
                                    self.firmware_dict,
                                    self._empty_configs)
    self.assertEqual(self._mock_push.call_count, 0)

  def testScheduleCrosSuccessfullyWithSpecifiedModel(self):
    """Test schedule unibuild with specific model."""
    self.task.board = self.UNIBUILD_BOARD
    branch_builds = {(self.UNIBUILD_BOARD, 'robo', 'release', '56'):
                     '0000.00.00',
                     (self.UNIBUILD_BOARD, 'lava', 'release', '56'):
                     '0000.00.00'}
    self.task._schedule_cros_builds(branch_builds,
                                    self.firmware_dict,
                                    self._fake_configs)
    self.assertEqual(self._mock_push.call_count, 2)

  def testScheduleCrosSuccessfullyForBoardWithSuffix(self):
    """Test schedule board with suffix and specific model."""
    branch_builds = {
        ('hatch-kernelnext', None, 'release', '56'): '0000.00.00'
    }
    self.task.boards = 'hatch-kernelnext'
    self.task.models = 'hatch_akemi'
    self.task._schedule_cros_builds(branch_builds, self.firmware_dict,
                                    self._fake_configs)
    self.assertEqual(self._mock_push.call_count, 1)

  def testScheduleCrosNonValidSpec(self):
    """Test schedule no cros builds due to non-allowed branch milestone."""
    branch_builds = {(self.BOARD, None, 'release', '56'): '0000.00.00'}
    # Only run tasks whose milestone = tot (R40)
    self.task.branch_specs = re.split(r'\s*,\s*', '==tot')
    self.task._set_spec_compare_info()
    self.task._schedule_cros_builds(branch_builds,
                                    self.firmware_dict,
                                    self._empty_configs)
    self.assertEqual(self._mock_push.call_count, 0)

  def testScheduleCrosSuccessfullyWithValidFirmware(self):
    """Test schedule cros builds successfully with valid firmware."""
    branch_builds = {(self.BOARD, None, 'release', '56'): '0000.00.00'}
    self.task.firmware_ro_build_spec = 'firmware'
    self.task._schedule_cros_builds(branch_builds,
                                    self.firmware_dict,
                                    self._fake_configs)
    self.assertEqual(self._mock_push.call_count, 1)

  def testScheduleCrosWithNonValidFirmware(self):
    """Test schedule no cros builds due to non-existent firmware."""
    branch_builds = {('foo-board', None, 'release', '56'): '0000.00.00'}
    self.task.firmware_ro_build_spec = 'firmware'
    self.task._schedule_cros_builds(branch_builds,
                                    self.firmware_dict,
                                    self._empty_configs)
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
        [], (branch_builds, []), self.firmware_dict, self._fake_configs))

  def testScheduleLaunchControlIsPushSuccessfully(self):
    """Test IS_PUSHED is changed if some launch control suites are scheduled."""
    lc_builds = {self.BOARD: ['git_nyc-mr2-release/shamu-userdebug/3844975',
                              'git_nyc-mr1-release/shamu-userdebug/3783920']}
    lc_branches = 'git_nyc-mr1-release,git_nyc-mr2-release'
    self.task.launch_control_branches = [
        t.lstrip() for t in lc_branches.split(',')]
    self.task.os_type = build_lib.OS_TYPES_LAUNCH_CONTROL
    self.assertTrue(self.task.schedule(
        lc_builds, ([], []), self.firmware_dict,
        self._empty_configs))

  def testScheduleCrosIsPushInvalidBoard(self):
    """Test schedule no cros builds due to non-allowed board."""
    branch_builds = (
        {('%s_2' % self.BOARD, None, 'release', '56'): '0000.00.00'}, {},
    )
    self.task.os_type = build_lib.OS_TYPE_CROS
    self.assertFalse(self.task.schedule(
        [], branch_builds, self.firmware_dict, self._empty_configs))

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
        lc_builds, ([], []), self.firmware_dict,
        self._empty_configs))


class TaskJobSectionTestCase(TaskBaseTestCase):

  def setUp(self):
    super(TaskJobSectionTestCase, self).setUp()
    mock_push = mock.patch('task_executor.push')
    self._mock_push = mock_push.start()
    self.addCleanup(mock_push.stop)

  def testJobSectionName(self):
    """Test the job section name if recorded."""
    self.task.schedule(
        [], ([], []), self.firmware_dict, self._fake_configs)
    self.assertEqual(self._mock_push.call_count, 0)
    job_sec = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ScheduleJobSection())
    self.assertEqual(job_sec.job_name, 'fake_name')

  def testAddBoard(self):
    """Test the configured board is recorded."""
    new_task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=[],
        boards='coral'))
    new_task.schedule(
        [], ([], []), self.firmware_dict, self._fake_configs)
    job_sec = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ScheduleJobSection())
    self.assertEqual(len(job_sec.build_targets), 1)
    self.assertEqual(job_sec.build_targets[0].name, 'coral')

  def testAddModel(self):
    """Test the configured model is recorded."""
    new_task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=[],
        boards='coral',
        exclude_models='coral_robo,coral_nasher'))
    new_task.schedule(
        [], ([], []), self.firmware_dict, self._fake_configs)
    job_sec = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ScheduleJobSection())
    # lava is the only coral model that was not excluded.
    self.assertEqual(len(job_sec.models), 1)
    self.assertEqual(job_sec.models[0].value, 'lava')

  def testAddMatchedBuild(self):
    """Test the matched build is recorded."""
    branch_builds = {('coral', '', 'release', '40'):
                     '0000.00.00',
                     ('hatch', '', 'release', '37'):
                     '0000.00.00'}
    new_task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=['>=tot-2'],
        boards='coral,hatch',
        os_type=build_lib.OS_TYPE_CROS))
    new_task.schedule(
            [], (branch_builds, []), self.firmware_dict, self._fake_configs)
    job_sec = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ScheduleJobSection())
    self.assertEqual(len(job_sec.matched_builds), 1)
    build = job_sec.matched_builds[0].release_build
    # hatch should not be recorded as its build is too old.
    self.assertEqual(build.build_target.name, 'coral')
    self.assertEqual(build.milestone, 40)
    self.assertEqual(build.chrome_os_version, '0000.00.00')
    self.assertEqual(build.type, branch_pb2.Branch.RELEASE)

  def testAddMatchedRelaxBuild(self):
    """Test the matched relax build is recorded."""
    relax_builds = {('coral', '', 'release', '40'):
                     '0000.00.00',
                     ('hatch', '', 'release', '37'):
                     '0000.00.00'}
    new_task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=['>=tot-2'],
        boards='coral,hatch',
        only_hwtest_sanity_required=True,
        os_type=build_lib.OS_TYPE_CROS))
    new_task.schedule(
            [], ([], relax_builds), self.firmware_dict, self._fake_configs)
    job_sec = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ScheduleJobSection())
    self.assertEqual(len(job_sec.matched_builds), 1)
    build = job_sec.matched_builds[0].relax_build
    # hatch should not be recorded as its build is too old.
    self.assertEqual(build.build_target.name, 'coral')
    self.assertEqual(build.milestone, 40)
    self.assertEqual(build.chrome_os_version, '0000.00.00')
    self.assertEqual(build.type, branch_pb2.Branch.RELEASE)

  def testAddMatchedFirmwareBuild(self):
    """Test the matched firmware build is recorded."""
    branch_builds = {('fake_board', '', 'release', '40'):
                     '0000.00.00'}
    new_task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=['>=tot-2'],
        boards='fake_board',
        firmware_rw_build_spec='firmware',
        os_type=build_lib.OS_TYPE_CROS))
    new_task.schedule(
            [], (branch_builds, []), self.firmware_dict, self._fake_configs)
    job_sec = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ScheduleJobSection())
    self.assertEqual(len(job_sec.matched_builds), 2)
    build = job_sec.matched_builds[1].firmware_rw_build
    self.assertEqual(build.build_target.name, 'fake_board')
    self.assertEqual(build.type, branch_pb2.Branch.FIRMWARE)
    self.assertEqual(build.artifact.path,
                     self.firmware_dict['firmware', 'fake_board'])

  def testScheduleJobSuccessfully(self):
    """Test the scheduled job is recorded."""
    branch_builds = {('coral', 'lava', 'release', '40'):
                     '0000.00.00'}
    new_task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=['>=tot-2'],
        boards='coral',
        os_type=build_lib.OS_TYPE_CROS))
    with mock.patch('uuid.uuid1', return_value=FAKE_UUID):
      new_task.schedule(
              [], (branch_builds, []), self.firmware_dict, self._fake_configs)
      job_sec = json_format.Parse(
            json.dumps(self.mock_bq_client.rows[0]['json']),
            analytics_pb2.ScheduleJobSection())
      self.assertEqual(len(job_sec.schedule_jobs), 1)
      job = job_sec.schedule_jobs[0]
      self.assertEqual(job.build_target.name, 'coral')
      self.assertEqual(job.model.value, 'lava')
      self.assertEqual(job.queued_task_id, FAKE_UUID)

  def testScheduleJobFailedforFirmwareRO(self):
    """Test the dropped job due to firmware absence is recorded."""
    branch_builds = {('coral', 'lava', 'release', '40'):
                     '0000.00.00'}
    new_task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=['>=tot-2'],
        boards='coral',
        firmware_ro_build_spec='firmware',
        firmware_ro_version=None,
        os_type=build_lib.OS_TYPE_CROS))
    new_task.schedule(
            [], (branch_builds, []), {}, self._fake_configs)
    job_sec = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ScheduleJobSection())
    self.assertEqual(len(job_sec.schedule_jobs), 1)
    job = job_sec.schedule_jobs[0]
    self.assertEqual(job.build_target.name, 'coral')
    self.assertEqual(job.model.value, 'lava')
    self.assertIn('No RO firmware build to run', job.justification)

  def testScheduleJobFailedforFirmwareRW(self):
    """Test the dropped job due to firmware absence is recorded."""
    branch_builds = {('coral', 'lava', 'release', '40'):
                     '0000.00.00'}
    new_task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=['>=tot-2'],
        boards='coral',
        firmware_rw_build_spec='firmware',
        firmware_rw_version=None,
        os_type=build_lib.OS_TYPE_CROS))
    new_task.schedule(
            [], (branch_builds, []), {}, self._fake_configs)
    job_sec = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ScheduleJobSection())
    self.assertEqual(len(job_sec.schedule_jobs), 1)
    job = job_sec.schedule_jobs[0]
    self.assertEqual(job.build_target.name, 'coral')
    self.assertEqual(job.model.value, 'lava')
    self.assertIn('No RW firmware build to run', job.justification)

  def testScheduleJobFailedforBranchNotMaching(self):
    """Test the dropped job due to branch spec is recorded."""
    branch_builds = {('coral', 'lava', 'release', '38'):
                     '0000.00.00'}
    new_task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=['>=tot-1'],
        boards='coral',
        os_type=build_lib.OS_TYPE_CROS))
    new_task.schedule(
            [], (branch_builds, []), {}, self._fake_configs)
    job_sec = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ScheduleJobSection())
    self.assertEqual(len(job_sec.schedule_jobs), 1)
    job = job_sec.schedule_jobs[0]
    self.assertEqual(job.build_target.name, 'coral')
    self.assertEqual(job.model.value, 'lava')
    self.assertIn('branch_build spec', job.justification)

  def testScheduleJobFailedforAnyModel(self):
    """Test the dropped job due to any_model is recorded."""
    branch_builds = {('coral', None, 'release', '38'):
                     '0000.00.00'}
    new_task = task.Task(task_config_reader.TaskInfo(
        name=self.NAME,
        suite=self.SUITE,
        branch_specs=['>=tot-2'],
        boards='coral',
        any_model=True,
        exclude_models='coral_nasher',
        os_type=build_lib.OS_TYPE_CROS))
    new_task.schedule(
            [], (branch_builds, []), {}, self._fake_configs)
    job_sec = json_format.Parse(
          json.dumps(self.mock_bq_client.rows[0]['json']),
          analytics_pb2.ScheduleJobSection())
    jobs = job_sec.schedule_jobs
    # 'nasher' is excluded, hence there should be two jobs for the rest models
    # 'robo', 'lava'.
    self.assertEqual(2, len(jobs))
    # The first job should be scheduled with empty model, as any_model is True.
    self.assertEqual(jobs[0].build_target.name, 'coral')
    self.assertEqual(jobs[0].model.value, '')
    # The second job should be skipped and the justification is recorded.
    self.assertEqual(jobs[1].build_target.name, 'coral')
    self.assertEqual(jobs[1].model.value, 'lava')
    self.assertIn('Skip model lava as any_model enabled', jobs[1].justification)

  def testScheduleJobForBoardWithSuffix(self):
    """Test record a schedule job with board plus suffix and model specified."""
    branch_builds = {('hatch-kernelnext', None, 'release', '38'): '0000.00.00'}
    new_task = task.Task(
        task_config_reader.TaskInfo(
            name=self.NAME,
            suite=self.SUITE,
            branch_specs=['>=tot-2'],
            boards='hatch-kernelnext',
            models='hatch_akemi',
            os_type=build_lib.OS_TYPE_CROS))
    new_task.schedule([], (branch_builds, []), {}, self._fake_configs)
    job_sec = json_format.Parse(
        json.dumps(self.mock_bq_client.rows[0]['json']),
        analytics_pb2.ScheduleJobSection())
    jobs = job_sec.schedule_jobs
    # Only the specified model should appear in the scheduled jobs.
    self.assertEqual(1, len(jobs))
    self.assertEqual(jobs[0].build_target.name, 'hatch-kernelnext')
    self.assertEqual(jobs[0].model.value, 'akemi')
