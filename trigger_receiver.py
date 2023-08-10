# Copyright 2023 The ChromiumOS Authors.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for cron job to trigger events for suite scheduler."""

import logging

import config_reader
import constants
import datastore_client
import file_getter
import rest_client
import StringIO
import task_config_reader

from google.appengine.api.runtime import runtime


class TriggerReceiver(object):
  """The class for receiving event triggers."""

  def __init__(self, fake=False):
    """Initialize a trigger receiver.

    Its job is to fetch triggers from config files and trigger them.
    """
    logging.warning("*******Start TriggerReceiver.__init__()*******\n%s*********************************", runtime.memory_usage())
    logging.warning("*******Start TriggerReceiver make bb client*******\n%s*********************************", runtime.memory_usage())
    self._build_client = rest_client.BuildBucketBigqueryClient(
        rest_client.BaseRestClient(
            constants.RestClient.BIGQUERY_CLIENT.scopes,
            constants.RestClient.BIGQUERY_CLIENT.service_name,
            constants.RestClient.BIGQUERY_CLIENT.service_version))
    logging.warning("*******End TriggerReceiver make bb client*******\n%s*********************************", runtime.memory_usage())
    logging.warning("*******Start TriggerReceiver make datastore client*******\n%s*********************************", runtime.memory_usage())
    self._last_exec_client = datastore_client.LastExecutionRecordStore()
    logging.warning("*******End TriggerReceiver make datastore client*******\n%s*********************************", runtime.memory_usage())
    logging.warning("*******Start TriggerReceiver make android build client*******\n%s*********************************", runtime.memory_usage())
    self._android_client = rest_client.AndroidBuildRestClient(
        rest_client.BaseRestClient(
            constants.RestClient.ANDROID_BUILD_CLIENT.scopes,
            constants.RestClient.ANDROID_BUILD_CLIENT.service_name,
            constants.RestClient.ANDROID_BUILD_CLIENT.service_version))
    logging.warning("*******End TriggerReceiver make android build client*******\n%s*********************************", runtime.memory_usage())
    if fake:
      logging.warning("*******Start TriggerReceiver make fake task config*******\n%s*********************************", runtime.memory_usage())
      self._task_config = task_config_reader.TaskConfig(
          config_reader.ConfigReader(
              file_getter.TEST_SUITE_SCHEDULER_CONFIG_FILE))
      logging.warning("*******End TriggerReceiver make fake task config*******\n%s*********************************", runtime.memory_usage())
      logging.warning("*******Start TriggerReceiver make fake lab config reader*******\n%s*********************************", runtime.memory_usage())
      fake_lab_config_reader = config_reader.ConfigReader(
          file_getter.TEST_LAB_CONFIG_FILE)
      logging.warning("*******End TriggerReceiver make fake lab config reader*******\n%s*********************************", runtime.memory_usage())
      logging.warning("*******Start TriggerReceiver make fake lab config *******\n%s*********************************", runtime.memory_usage())
      self._lab_config = config_reader.LabConfig(fake_lab_config_reader)
      logging.warning("*******End TriggerReceiver make fake lab config *******\n%s*********************************", runtime.memory_usage())
    else:
      logging.warning("*******Start TriggerReceiver cloning config*******\n%s*********************************", runtime.memory_usage())
      file_getter.clone_config()
      logging.warning("*******End TriggerReceiver cloning config*******\n%s*********************************", runtime.memory_usage())
      logging.warning("*******Start TriggerReceiver make task config reader*******\n%s*********************************", runtime.memory_usage())
      self._task_config = task_config_reader.TaskConfig(
          config_reader.ConfigReader(
                file_getter.NEW_SUITE_SCHEDULER_CONFIG_FILE))
      logging.warning("*******End TriggerReceiver make task config reader*******\n%s*********************************", runtime.memory_usage())
      logging.warning("*******Start TriggerReceiver make task config*******\n%s*********************************", runtime.memory_usage())
      lab_config_reader = config_reader.ConfigReader(file_getter.NEW_LAB_CONFIG_FILE)
      logging.warning("*******End TriggerReceiver make task config*******\n%s*********************************", runtime.memory_usage())
      logging.warning("*******Start TriggerReceiver make lab config*******\n%s*********************************", runtime.memory_usage())
      self._lab_config = config_reader.LabConfig(lab_config_reader)
      logging.warning("*******End TriggerReceiver make lab config*******\n%s*********************************", runtime.memory_usage())

    # Initialize events
    self.events = {}
    logging.warning("*******Start TriggerReceiver initialize events*******\n%s*********************************", runtime.memory_usage())
    for keyword, klass in task_config_reader.EVENT_CLASSES.iteritems():
      logging.info('Initializing %s event', keyword)
      logging.warning("*******Start TriggerReceiver initialize %s event*******\n%s*********************************",keyword, runtime.memory_usage())
      new_event = klass(
          self._task_config.get_event_setting(klass.section_name()),
          self._last_exec_client.get_last_execute_time(klass.KEYWORD))

      if new_event.should_handle:
        new_event.set_task_list(
            self._task_config.get_tasks_by_keyword(klass.KEYWORD)['tasks'])
        logging.info('Got %d tasks for %s event',
                     len(new_event.task_list), klass.KEYWORD)

      self.events[keyword] = new_event
      logging.warning("*******End TriggerReceiver initialize %s event*******\n%s*********************************",keyword, runtime.memory_usage())
    logging.warning("*******End TriggerReceiver initialize events*******\n%s*********************************", runtime.memory_usage())

    self.event_results = {}
    logging.warning("*******End TriggerReceiver.__init__()*******\n%s*********************************", runtime.memory_usage())


  def cron(self):
    """The cron job to scheduler suite jobs by config.

    This cron job executes:
      1. Filter out the tasks that shoud be run at this round.
      2. Fetch launch_control_build for Android boards from API.
      3. Fetch cros_builds for ChromeOS boards from Buildbucket bigquery.
      4. Schedule corresponding jobs with fetched builds.
      5. Reset event when it's finished.
    """
    logging.warning("*******Start trigger_reciver.cron()*******\n%s*********************************", runtime.memory_usage())
    for keyword, event in self.events.iteritems():
      logging.info('Handling %s event in cron job', keyword)

      event.filter_tasks()
      if event.task_list:
        logging.info('Processing %d tasks.', len(event.task_list))
        self._schedule_tasks(event)
      else:
        logging.info('No task list found')
      event.finish()
    logging.warning("*******End trigger_reciver.cron()*******\n%s*********************************", runtime.memory_usage())

  def _schedule_tasks(self, event):
    """Schedule tasks based on given event.

    Args:
      event: a kind of event, which contains its tasks that should be
        scheduled.
    """
    logging.warning("*******Start trigger_reciver._schedule_tasks()*******\n%s*********************************", runtime.memory_usage())
    cros_builds_tuple = event.get_cros_builds(
        self._lab_config, self._build_client)
    logging.debug('Found CrOS builds: %r', cros_builds_tuple)
    # Set delta to 3 days here as we only build once per day for non tot
    # builds, so a single failure on secondary boards may cause a skip
    # of primary board.
    recent_cros_builds_tuple = event.get_recent_cros_builds(
        self._lab_config, self._build_client, delta_days=3)
    logging.debug('Found recent CrOS builds: %r', recent_cros_builds_tuple)
    launch_control_builds = event.get_launch_control_builds(
        self._lab_config, self._android_client)
    logging.debug('Found launch_control_builds: %r', launch_control_builds)
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
    logging.info('Finished processing all tasks')
    logging.warning("*******End trigger_reciver._schedule_tasks()*******\n%s*********************************", runtime.memory_usage())
