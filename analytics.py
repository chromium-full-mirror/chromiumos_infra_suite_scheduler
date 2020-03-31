# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for collecting and uploading analytics metrics."""

import json
import logging
import re

import constants
import rest_client

from chromite.api.gen.test_platform.suite_scheduler import analytics_pb2
from chromite.api.gen.chromite.api import artifacts_pb2
from chromite.api.gen.chromiumos import branch_pb2
from chromite.api.gen.chromiumos import common_pb2

from google.protobuf import timestamp_pb2
from google.protobuf import json_format


class AnalyticsError(Exception):
  """Raised when there is a general error."""


class AnalyticsBase(object):
  """Base class to handle analytics data."""

  def __init__(self, table, message):
    """Initialize a base event.

    Args:
      table: string of the table name.
      message: protobuf object to upload.
    """
    self.bq_client = _gen_bq_client(table)
    self.message = message

  def upload(self):
    """Convey protobuf to json and insert to BQ."""
    rows = [{
        'json':
            json.loads(
                json_format.MessageToJson(
                    self.message,
                    preserving_proto_field_name=True,
                    including_default_value_fields=True))
    }]
    return self.bq_client.insert(rows)

class ExecutionTask(AnalyticsBase):
  """Track the execution for the queued tasks."""

  def __init__(self, task_id):
    """Initialize an ExcutionTask.

    Args:
      task_id: string of uuid, assigned by the event which created this task.
    """
    self.task = analytics_pb2.ExecutionTask(
        queued_task_id=task_id,
        request_sent=timestamp_pb2.Timestamp())
    self.task.request_sent.GetCurrentTime()
    super(ExecutionTask, self).__init__(constants.Metrics.EXECUTION_TASK_TABLE,
       self.task)

  def update_result(self, resp):
    """Attach the buildbucket id to task_execution.

    Args:
      resp: build_pb2.Build object of Buildbucket response.
    """
    try:
      if resp.id > 0:
        self.task.response.ctp_build_id = str(resp.id)
        return
      # If id is absent, we should log resp as an error message.
      logging.warning('No build id in buildbucket response %s.', str(resp))
    except AttributeError as e:
      logging.warning('Failed to parse the buildbucket response, %s.'
                      'Error: %s', str(resp), str(e))
    self.task.error.error_message = str(resp)


class ScheduleJobSection(AnalyticsBase):
  """Record all the scheduling decisions in a job section."""

  def __init__(self, task_info):
    """Initialize a ScheduleJobSection

    Args:
      task_info: a config_reader.TaskInfo object.
    """
    self.job_section = _job_section(task_info)
    self.bq_client = _gen_bq_client(constants.Metrics.TRIGGER_EVENT_TABLE)
    super(ScheduleJobSection, self).__init__(
        constants.Metrics.TRIGGER_EVENT_TABLE,
        self.job_section)

  def add_board(self, board):
    """Add a board to job_section.

    Boards added are the target, on which we schedule the configured
    suite test.

    Args:
      board: a string of board name.
    """
    self.job_section.build_targets.add(name=board)

  def add_model(self, model):
    """Add a model to job_section.

    Models added are the target, on which we schedule the configured
    suite test. If not set in the config, all models under the boards in this
    section will be appended.

    Args:
      model: a string of model name.
    """
    self.job_section.models.add(value=model)

  def add_matched_build(self, board, build_type, milestone, manifest):
    """Add an eligible build for this job section.

    Args:
      board: a string of board name.
      build_type: a string of build type with the board, like 'release'.
      milestone: a string milestone, like '80'.
      manifest: a string of chromeos version, e.g. '12240.0.0'.
    """
    self.job_section.matched_builds.add(release_build=analytics_pb2.BuildInfo(
        build_target=common_pb2.BuildTarget(name=board),
        milestone=int(milestone),
        chrome_os_version=manifest,
        type=_branch_type(build_type)))

  def add_matched_relax_build(self, board, build_type, milestone, manifest):
    """Add an eligible relax build for this job section.

    Args:
      board: a string of board name.
      build_type: a string of build type with the board, like 'release'.
      milestone: a string milestone, like '80'.
      manifest: a string of chromeos version, e.g. '12240.0.0'.
    """
    self.job_section.matched_builds.add(relax_build=analytics_pb2.BuildInfo(
        build_target=common_pb2.BuildTarget(name=board),
        milestone=int(milestone),
        chrome_os_version=manifest,
        type=_branch_type(build_type)))

  def add_matched_fw_build(self, board, build_type, artifact, read_only=True):
    """Add an eligible firmware build for this job section.

    Args:
      board: a string of board name.
      build_type: a string of build type with the board, like 'release'.
      artifact: relative path to the artifact file, e.g.
        'firmware-board-12345.67.B-firmwarebranch/RFoo-1.0.0-b1e234567/board'.
      read_only: a boolean if true for RO firmware build and false for RW firmware.
    """
    firmware_build = analytics_pb2.FirmwareBuildInfo(
              build_target=common_pb2.BuildTarget(name=board),
              artifact=artifacts_pb2.Artifact(path=artifact),
              type=_branch_type(build_type))
    if read_only:
      self.job_section.matched_builds.add(
          firmware_ro_build=firmware_build)
    else:
      self.job_section.matched_builds.add(
          firmware_rw_build=firmware_build)

  def add_schedule_job(self, board, model, msg=None, task_id=None):
    """Add a schedule job.

    Args:
      board: a string of board name.
      model: a string of model name.
      msg: a string of the reason we drop this build.
      task_id: a string of uuid to track it in taskqueue.

    Raise:
      AnalyticsError: if both msg/task_id are specified or both are None.
    """
    if all([msg, task_id]):
      raise AnalyticsError('msg and task_id should not be set both; got'
          'msg: %s, task_id: %s.' % (msg, task_id))
    if not any([msg, task_id]):
      raise AnalyticsError('At least one of msg and task_id should '
          'be set; got msg: %s, task_id: %s.' % (msg, task_id))
    new_job = self.job_section.schedule_jobs.add(
        generated_time=timestamp_pb2.Timestamp())
    if model:
      new_job.model.value = model
    new_job.build_target.name = board
    if msg:
      new_job.justification = msg
    if task_id:
      new_job.queued_task_id = task_id
    new_job.generated_time.GetCurrentTime()


def _gen_bq_client(table):
  """A wrapper to generate Bigquery REST client.

  Args:
    table: string of the table name.

  Returns:
    REST client for Bigquery API.
  """
  project = constants.Metrics.PROJECT_ID_STAGING
  if (constants.environment() == constants.RunningEnv.ENV_PROD and
      constants.application_id() == constants.AppID.PROD_APP):
    project = constants.Metrics.PROJECT_ID
  return rest_client.BigqueryRestClient(
      rest_client.BaseRestClient(
          constants.RestClient.BIGQUERY_CLIENT.scopes,
          constants.RestClient.BIGQUERY_CLIENT.service_name,
          constants.RestClient.BIGQUERY_CLIENT.service_version),
      project=project,
      dataset=constants.Metrics.DATASET,
      table=table)


def _parse_branch_spec(spec):
  """A wrapper to parse the branch spec into channcel and lag.

  Args:
    spec: string of branch spec, e.g. '>=tot-2', '==tot'

  Returns:
    channel: analytics_pb2.BranchFilter for the builder type.
    lag: number of minor versions behind tip-of-tree.

  Raise:
      AnalyticsError: if the spec are not supported.
  """
  if not 'tot' in spec:
    raise ValueError('Only support branch specs relative to tot, '
                     'e.g. >=tot-2, got %s' % spec)
  if spec[:2] not in ["<=", ">=", "=="]:
    raise ValueError('Only "<=", ">=", "==" are supported, '
                     'e.g. >=tot-2, got %s' % spec)
  to_operator = {
       "==": analytics_pb2.BranchFilter.EQ,
       ">=": analytics_pb2.BranchFilter.GE,
       "<=": analytics_pb2.BranchFilter.LE}
  TOT_SPEC = r'.*tot-(?P<lag>.+)'
  match = re.match(TOT_SPEC, spec)
  if not match:
    return analytics_pb2.BranchFilter.MASTER, to_operator[spec[:2]], 0
  lag = match.group('lag')
  if lag.isdigit():
    return analytics_pb2.BranchFilter.MASTER, to_operator[spec[:2]], int(lag)
  raise ValueError('Failed to get the lag number from spec, %s' % spec)


def _job_section(task_info):
  """A wrapper to generate job_section from task_info.

  Args:
    task_info: a config_reader.TaskInfo object.

  Returns:
    job_section: a analytics_pb2.ScheduleJobSection object.
  """
  job_section = analytics_pb2.ScheduleJobSection(
      job_name=task_info.name, pool=task_info.pool, suite=task_info.suite)
  if task_info.hour:
    job_section.schedule_job_trigger.nightly.hour = task_info.hour
  elif task_info.day:
    job_section.schedule_job_trigger.weekly.day = task_info.day
  else:
    job_section.schedule_job_trigger.interval.pause = 0
  build_filters = job_section.schedule_job_trigger.build_filters
  build_filters.only_hwtest_sanity_required = (
      task_info.only_hwtest_sanity_required is not None)
  if task_info.branch_specs:
    for spec in task_info.branch_specs:
      try:
        channel, op, lag = _parse_branch_spec(spec)
        build_filters.branch_filters.add(
            channel=channel, operator=op, lag=lag)
      except ValueError as e:
        logging.warning('Failed to parse the spec, %s', str(e))
  if task_info.firmware_rw_build_spec:
    build_filters.firmware_rw_build_spec = branch_pb2.Branch.FIRMWARE
  if task_info.firmware_ro_build_spec:
    build_filters.firmware_ro_build_spec = branch_pb2.Branch.FIRMWARE
  return job_section


def _branch_type(build_type):
  if build_type == "release":
    return branch_pb2.Branch.RELEASE
  if build_type == "firmware":
    return branch_pb2.Branch.FIRMWARE
  return branch_pb2.Branch.UNSPECIFIED
