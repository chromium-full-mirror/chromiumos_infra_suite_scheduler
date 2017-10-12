# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for cron job to trigger events for suite scheduler."""

import logging

import cloud_sql_client
import config_reader
import constants
import datastore_client
import file_getter
import rest_client


class TriggerReceiver(object):
  """The class for receiving event triggers."""

  def __init__(self):
    """Initialize a trigger receiver.

    Its job is to fetch triggers from config files and trigger them.
    """
    self._cidb_client = cloud_sql_client.CIDBClient('CIDB', 'cidb')
    self._last_exec_client = datastore_client.LastExecutionRecordStore()
    self._android_client = rest_client.AndroidBuildRestClient(
        rest_client.BaseRestClient(
            constants.RestClient.ANDROID_BUILD_CLIENT.scopes,
            constants.RestClient.ANDROID_BUILD_CLIENT.service_name,
            constants.RestClient.ANDROID_BUILD_CLIENT.service_version))

    task_config_reader = config_reader.ConfigReader(
        file_getter.SUITE_SCHEDULER_CONFIG_FILE)
    self._task_config = config_reader.TaskConfig(task_config_reader)
    lab_config_reader = config_reader.ConfigReader(
        file_getter.LAB_CONFIG_FILE)
    self._lab_config = config_reader.LabConfig(lab_config_reader)

    # Initialize events
    self.events = {}
    for keyword, klass in config_reader.EVENT_CLASSES.iteritems():
      logging.info('Initializing %s event', keyword)
      new_event = klass(
          self._task_config.get_event_setting(klass.section_name()),
          self._last_exec_client.get_last_execute_time(klass.KEYWORD))

      if new_event.should_handle:
        new_event.set_task_list(
            self._task_config.get_tasks_by_keyword(klass.KEYWORD)['tasks'])
        logging.info('Got %d tasks for %s event',
                     len(new_event.task_list), klass.KEYWORD)

      self.events[keyword] = new_event

    self.event_results = {}

  def cron(self):
    """The cron job to scheduler suite jobs by config.

    This cron job executes:
      1. Filter out the tasks that shoud be run at this round.
      2. Fetch launch_control_build for Android boards from API.
      3. Fetch cros_builds for ChromeOS boards from CIDB.
      4. Schedule corresponding jobs with fetched builds.
      5. Reset event when it's finished.
    """
    for keyword, event in self.events.iteritems():
      logging.info('Handling %s event in cron job', keyword)

      event.filter_tasks()
      if event.task_list:
        logging.info('Processing %d tasks.', len(event.task_list))
        self._schedule_tasks(event)
      else:
        logging.info('No task list found')
      event.finish()

  def _schedule_tasks(self, event):
    """Schedule tasks based on given event.

    Args:
      event: a kind of event, which contains its tasks that should be
        scheduled.
    """
    cros_builds = event.get_cros_builds(self._cidb_client)
    logging.debug('Found CrOS builds: %r', cros_builds)
    launch_control_builds = event.get_launch_control_builds(
        self._lab_config, self._android_client)
    logging.debug('Found launch_control_builds: %r', launch_control_builds)

    self.event_results[event.KEYWORD] = event.process_tasks(
        launch_control_builds=launch_control_builds,
        cros_builds=cros_builds,
        lab_config=self._lab_config,
        db_client=self._cidb_client)
    logging.info('Finished processing all tasks')
