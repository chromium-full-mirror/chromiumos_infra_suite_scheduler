#!/usr/bin/env python2
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for analytics unittests."""

import uuid
import unittest

import analytics
import task_config_reader

from chromite.api.gen.test_platform.suite_scheduler import analytics_pb2
from chromite.api.gen.chromiumos import branch_pb2
from infra_libs.buildbucket.proto import build_pb2
from infra_libs.buildbucket.proto import common_pb2


def _get_task_info():
  return task_config_reader.TaskInfo(
            name='FakeSuiteTestPerBuild',
            analytics_name='FakeSuiteTestPerBuild',
            suite='fake_suite',
            pool='fake_pool',
            num=1,
            hour=5,
            boards='coral,hana,hatch',
            branch_specs=['>=tot-2', '==tot'],
            priority=50,
            timeout=600)


class TestExecutionTask(unittest.TestCase):

  def setUp(self):
    super(TestExecutionTask, self).setUp()

  def testTaskID(self):
    tid = str(uuid.uuid1())
    execution = analytics.ExecutionTask(tid, 'fake_req_tag')
    self.assertEqual(execution.task.queued_task_id, tid)
    self.assertEqual(execution.task.request_tag, 'fake_req_tag')

  def testUpdateResultBuildID(self):
    execution = analytics.ExecutionTask(str(uuid.uuid1()), '')
    bid = 8890493019851395280
    execution.update_result(build_pb2.Build(id=bid))
    self.assertEqual(execution.task.response.ctp_build_id, str(bid))

  def testUpdateResultInvalidBuildID(self):
    execution = analytics.ExecutionTask(str(uuid.uuid1()), '')
    execution.update_result(build_pb2.Build(status=common_pb2.INFRA_FAILURE))
    self.assertIn('status: INFRA_FAILURE',
                  execution.task.error.error_message)

  def testUpdateResultErrorMsg(self):
    execution = analytics.ExecutionTask(str(uuid.uuid1()), '')
    msg = 'some error'
    execution.update_result(msg)
    self.assertEqual(execution.task.error.error_message, msg)


class TestScheduleJobSection(unittest.TestCase):

  def setUp(self):
    super(TestScheduleJobSection, self).setUp()

  def testJobInfo(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    self.assertEqual(client.message.job_name, 'FakeSuiteTestPerBuild')
    self.assertEqual(client.message.pool, 'fake_pool')
    self.assertEqual(client.message.suite, 'fake_suite')

  def testBuildFilters(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    job_trigger = client.message.schedule_job_trigger
    self.assertFalse(
        job_trigger.build_filters.only_hwtest_sanity_required)
    branch_filters = job_trigger.build_filters.branch_filters
    self.assertEqual(len(branch_filters), 2)
    self.assertEqual(branch_filters[0].channel,
        analytics_pb2.BranchFilter.MASTER)
    self.assertEqual(branch_filters[0].operator, analytics_pb2.BranchFilter.GE)
    self.assertEqual(branch_filters[0].lag, 2)
    self.assertEqual(branch_filters[1].channel,
        analytics_pb2.BranchFilter.MASTER)
    self.assertEqual(branch_filters[1].operator, analytics_pb2.BranchFilter.EQ)
    self.assertEqual(branch_filters[1].lag, 0)

  def testGenScheduleJobTriggerDaily(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    job_trigger = client.message.schedule_job_trigger
    self.assertEqual(job_trigger.nightly.hour, 5)

  def testGenScheduleJobTriggerEveryRun(self):
    task_info = task_config_reader.TaskInfo(
            name='FakeSuiteTestPerBuild',
            suite='fake_suite',
            pool='fake_pool')
    client = analytics.ScheduleJobSection(task_info)
    job_trigger = client.message.schedule_job_trigger
    self.assertEqual(job_trigger.interval.pause, 0)

  def testAddBoard(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    client.add_board('foo_board')
    self.assertEqual(len(client.message.build_targets), 1)
    self.assertEqual(client.message.build_targets[0].name, 'foo_board')

  def testAddModel(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    client.add_model('foo_model')
    self.assertEqual(len(client.message.models), 1)
    self.assertEqual(client.message.models[0].value, 'foo_model')

  def testAddMatchedBuild(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    client.add_matched_build('foo_board', 'release', '81', '12345.6.7')
    self.assertEqual(len(client.message.matched_builds), 1)
    match = client.message.matched_builds[0]
    self.assertEqual(match.release_build.build_target.name, 'foo_board')
    self.assertEqual(match.release_build.milestone, 81)
    self.assertEqual(match.release_build.chrome_os_version, '12345.6.7')
    self.assertEqual(match.release_build.type, branch_pb2.Branch.RELEASE)

  def testAddMatchedRelaxBuild(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    client.add_matched_relax_build('foo_board', 'release', '81', '12345.6.7')
    self.assertEqual(len(client.message.matched_builds), 1)
    match = client.message.matched_builds[0]
    self.assertEqual(match.relax_build.build_target.name, 'foo_board')
    self.assertEqual(match.relax_build.milestone, 81)
    self.assertEqual(match.relax_build.chrome_os_version, '12345.6.7')
    self.assertEqual(match.relax_build.type, branch_pb2.Branch.RELEASE)

  def testAddMatchedFWBuild(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    artifact = 'gs://image/firmware-foo-firmwarebranch/RNone-1.0.0-b123/foo'
    client.add_matched_fw_build(
        'foo_board', 'firmware', artifact, read_only=True)
    self.assertEqual(len(client.message.matched_builds), 1)
    match = client.message.matched_builds[0]
    self.assertEqual(
        match.firmware_ro_build.build_target.name, 'foo_board')
    self.assertEqual(match.firmware_ro_build.artifact.path, artifact)
    self.assertEqual(match.firmware_ro_build.type, branch_pb2.Branch.FIRMWARE)

  def testAddScheduleJob(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    client.add_schedule_job('foo_board', 'foo_model', task_id='b123456789')
    self.assertEqual(len(client.message.schedule_jobs), 1)
    job = client.message.schedule_jobs[0]
    self.assertEqual(job.queued_task_id, 'b123456789')

  def testAddFailedJob(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    client.add_schedule_job('foo_board', 'foo_model', msg='some error')
    self.assertEqual(len(client.message.schedule_jobs), 1)
    job = client.message.schedule_jobs[0]
    self.assertEqual(job.justification, 'some error')

  def testAddJobwithEmptyModel(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    client.add_schedule_job('foo_board', None, msg='some error')
    self.assertEqual(len(client.message.schedule_jobs), 1)
    job = client.message.schedule_jobs[0]
    self.assertEqual(job.justification, 'some error')

  def testAddScheduleJobRaiseError(self):
    client = analytics.ScheduleJobSection(_get_task_info())
    self.assertRaises(analytics.AnalyticsError,
        client.add_schedule_job,
        'foo_board',
        'foo_model',
        'some error',
        'b123456789')
    self.assertRaises(analytics.AnalyticsError,
        client.add_schedule_job,
        'foo_board',
        'foo_model')
