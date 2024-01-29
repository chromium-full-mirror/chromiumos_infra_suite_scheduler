# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for cron job to trigger events for suite scheduler."""

import safe_log

import config_reader
import constants
import datastore_client
import file_getter
import rest_client
import StringIO
import task_config_reader

from chromite.third_party.infra_libs.buildbucket.proto import builder_common_pb2



class TriggerReceiver(object):
  """The class for receiving event triggers."""

  def __init__(self, fake=False):
    """Initialize a trigger receiver.

    Its job is to fetch triggers from config files and trigger them.
    """

    # Set default builder based on the env.
    builder_name = constants.Buildbucket.STAGING_BUILDER
    if (constants.environment() == constants.RunningEnv.ENV_PROD
      and constants.application_id() == constants.AppID.PROD_APP):
      builder_name = constants.Buildbucket.PROD_BUILDER

    builder = builder_common_pb2.BuilderID(project=constants.Buildbucket.PROJECT,
                                        bucket=constants.Buildbucket.BUCKET,
                                        builder=builder_name)

    self._build_client = rest_client.BuildBucketBigqueryClient(
        rest_client.BaseRestClient(
            constants.RestClient.BIGQUERY_CLIENT.scopes,
            constants.RestClient.BIGQUERY_CLIENT.service_name,
            constants.RestClient.BIGQUERY_CLIENT.service_version))
    self._last_exec_client = datastore_client.LastExecutionRecordStore()
    self._android_client = rest_client.AndroidBuildRestClient(
        rest_client.BaseRestClient(
            constants.RestClient.ANDROID_BUILD_CLIENT.scopes,
            constants.RestClient.ANDROID_BUILD_CLIENT.service_name,
            constants.RestClient.ANDROID_BUILD_CLIENT.service_version))
    if fake:
      self._task_config = task_config_reader.TaskConfig(
          config_reader.ConfigReader(
              file_getter.TEST_SUITE_SCHEDULER_CONFIG_FILE), builder)
      fake_lab_config_reader = config_reader.ConfigReader(
          file_getter.TEST_LAB_CONFIG_FILE)
      self._lab_config = config_reader.LabConfig(fake_lab_config_reader)
    else:
      file_getter.clone_config()
      self._task_config = task_config_reader.TaskConfig(
          config_reader.ConfigReader(
                file_getter.NEW_SUITE_SCHEDULER_CONFIG_FILE), builder)
      lab_config_reader = config_reader.ConfigReader(file_getter.NEW_LAB_CONFIG_FILE)
      self._lab_config = config_reader.LabConfig(lab_config_reader)

    # Initialize events
    self.events = {}
    for keyword, klass in task_config_reader.EVENT_CLASSES.iteritems():
      safe_log.info('Initializing %s event', keyword)
      new_event = klass(
          self._task_config.get_event_setting(klass.section_name()),
          self._last_exec_client.get_last_execute_time(klass.KEYWORD))

      if new_event.should_handle:
        new_event.set_task_list(
            self._task_config.get_tasks_by_keyword(klass.KEYWORD)['tasks'])
        safe_log.info('Got %d tasks for %s event',
                     len(new_event.task_list), klass.KEYWORD)

      self.events[keyword] = new_event

    self.event_results = {}


  def cron(self):
    """The cron job to scheduler suite jobs by config.

    This cron job executes:
      1. Filter out the tasks that shoud be run at this round.
      2. Fetch launch_control_build for Android boards from API.
      3. Fetch cros_builds for ChromeOS boards from Buildbucket bigquery.
      4. Schedule corresponding jobs with fetched builds.
      5. Reset event when it's finished.
    """
    for keyword, event in self.events.iteritems():
      safe_log.info('Handling %s event in cron job', keyword)

      event.filter_tasks()
      if event.task_list:
        safe_log.info('Processing %d tasks.', len(event.task_list))
        self._schedule_tasks(event)
      else:
        safe_log.info('No task list found')
      event.finish()

  def _schedule_tasks(self, event):
    """Schedule tasks based on given event.

    Args:
      event: a kind of event, which contains its tasks that should be
        scheduled.
    """
    cros_builds_tuple = event.get_cros_builds(
        self._lab_config, self._build_client)
    # NOTE: Logging removed due to LogExplorer limitations.
    #safe_log.debug('Found CrOS builds: %r', cros_builds_tuple)
    # Set delta to 3 days here as we only build once per day for non tot
    # builds, so a single failure on secondary boards may cause a skip
    # of primary board.
    recent_cros_builds_tuple = event.get_recent_cros_builds(
        self._lab_config, self._build_client, delta_days=3)
    # NOTE: Logging removed due to LogExplorer limitations.
    #safe_log.debug('Found recent CrOS builds: %r', recent_cros_builds_tuple)
    launch_control_builds = event.get_launch_control_builds(
        self._lab_config, self._android_client)
    # NOTE: Logging removed due to LogExplorer limitations.
    #safe_log.debug('Found launch_control_builds: %r', launch_control_builds)
    firmware_builds = None
    if [x for x in event.task_list if (x.firmware_rw_build_spec or
                                       x.firmware_ro_build_spec)]:
      firmware_builds = event.get_firmware_builds(self._build_client)

    self.event_results[event.KEYWORD] = event.process_tasks(
        launch_control_builds=launch_control_builds,
        cros_builds_tuple=cros_builds_tuple,
        firmware_builds=firmware_builds,
        configs=config_reader.Configs(lab_config=self._lab_config),
        recent_cros_builds_tuple=recent_cros_builds_tuple)
    safe_log.info('Finished processing all tasks')
