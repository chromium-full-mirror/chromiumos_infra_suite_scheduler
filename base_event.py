# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module of a basic event."""

import datetime
import logging

import build_lib
import constants
import datastore_client
import global_config
import task

# The suffix for section
_SECTION_SUFFIX = '_params'


class BaseEvent(object):
  """Basic class for a suite scheduler event."""

  # The default keyword and priority for base event. Will be overwritten by
  # its subclass.
  KEYWORD = 'base'
  PRIORITY = constants.Priorities.DEFAULT

  # The interval hours between consequent rounds of events. Default is 6.
  LAST_EXEC_INTERVAL = 6

  # The number of days between each event to trigger. Default is 1.
  DAYS_INTERVAL = 1

  # The max lifetime of suites kicked off by this event.
  TIMEOUT = 24  # Hours

  def __init__(self, event_settings, last_exec_utc, target_exec_utc):
    """Initialize a base event.

    Args:
      event_settings: a config_reader.EventSettings object, indicating
        the event settings.
      last_exec_utc: The utc datetime.datetime timestamp of the last
        execution of the event.
      target_exec_utc: The utc datetime.datetime timestamp of the next
        execution of the event.
    """
    self._update_with_settings(event_settings)
    self._datastore_client = None
    self.task_list = []

    # Processing executing time.
    self.target_exec_utc = target_exec_utc
    self._set_last_exec(last_exec_utc)
    self._set_should_handle()

    logging.info('%s Event created:\ntarget_exec_time (utc): %s\n'
                 'last_exec_time (utc): %s\nshould_handle: %s',
                 self.keyword, self.target_exec_utc, self.last_exec_utc,
                 self.should_handle)

  def set_task_list(self, task_list):
    """Update task list with given input.

    Args:
      task_list: a new task list for this event.
    """
    self.task_list = list(task_list)

  def filter_tasks(self):
    """Filter tasks from original task list.

    This could be overwritten by subclass of BaseEvent, like Nightly event, or
    be directly used by event types like NewBuild.
    """
    self.task_list = list(self.task_list)

  def get_cros_builds(self, lab_config, build_client):
    """Get CrOS builds to run on for this event.

    Args:
      lab_config: a config_reader.LabConfig object, to read lab configs.
      build_client: a rest_client.BuildBucketBigqueryClient object, to
        connect Buildbucket Bigquery.

    Returns:
      A two-tuples of dicts containing cros builds, see return from
        |build_lib.get_cros_builds_since_date|.
    """
    return build_lib.get_cros_builds_since_date(
        build_client, lab_config.get_cros_board_list(), self.since_date)

  def get_launch_control_builds(self, lab_config, android_client):
    """Get launch control builds to run on for this event.

    Args:
      lab_config: a config_reader.LabConfig object, to read lab configs.
      android_client: a rest_client.AndroidBuildRestClient object to call
        android build API.

    Returns:
      a dict containing launch control builds for Android boards. See return
        value of |build_lib.get_launch_control_builds_by_branch_targets|.
    """
    return build_lib.get_launch_control_builds_by_branch_targets(
        android_client, lab_config.get_android_board_list(),
        self.launch_control_branch_targets)

  def process_tasks(self, launch_control_builds, cros_builds_tuple,
                    configs, build_client):
    """Schedule tasks in task_list.

    Args:
      launch_control_builds: the build dict for Android boards, see
        return value of |get_launch_control_builds|.
      cros_builds_tuple: a two-tuple of build dicts for ChromeOS boards,
        see return value of |get_cros_builds|.
      configs: a config_reader.Configs object, to contain several config
        readers.
      build_client: a rest_client.BuildBucketBigqueryClient object, to
        connect Buildbucket Bigquery.

    Returns:
      A list of finished tasks' names.
    """
    scheduled_tasks = []
    for per_task in self.task_list:
      try:
        if per_task.schedule(launch_control_builds, cros_builds_tuple,
                             configs, build_client):
          scheduled_tasks.append(per_task.name)
        else:
          logging.debug('No suites are scheduled in suites queue for '
                        'task %s', per_task.name)
      except task.SchedulingError:
        logging.exception('Failed to schedule task: %s', per_task.name)
        continue

    return scheduled_tasks

  def finish(self):
    """Execute all actions that once an event is finished."""
    self.datastore_client.set_last_execute_time(
        self.keyword, self.target_exec_utc)

  def _update_with_settings(self, event_settings):
    """Update event with given settings from config file.

    Args:
      event_settings: a config_reader.EventSettings object, indicating
        the event settings.
    """
    self.always_handle = event_settings.always_handle is not None
    if self.always_handle:
      self.always_handle = event_settings.always_handle

  def _set_last_exec(self, last_exec_utc):
    """Process and set last execute time.

    Set last_exec_utc. If last_exec_utc is too old or None, set it as
    target_exec_utc.

    Args:
      last_exec_utc: the utc datetime.datetime timestamp of last execute
        time. None means no last_exec_utc saved for this event in
        datastore.
    """
    if last_exec_utc is not None:
      self.last_exec_utc = last_exec_utc

      # If this TimedEvent has expired for a period of time, run its
      # tasks on next available timepoint.
      if (self.target_exec_utc - self.last_exec_utc > datetime.timedelta(
          hours=self.LAST_EXEC_INTERVAL)):
        self.last_exec_utc = self.target_exec_utc
    else:
      self.last_exec_utc = self.target_exec_utc

  def _set_should_handle(self):
    """Update it's the time for the event to be handled."""
    if self.always_handle or global_config.GAE_TESTING:
      self.should_handle = True
    else:
      if self.last_exec_utc and self.last_exec_utc == self.target_exec_utc:
        self.should_handle = False
      else:
        self.should_handle = True

  @classmethod
  def section_name(cls):
    """Getter for the section name of the event.

    Returns:
      A string representing section name, refers to a section in config file
        that contains this event's params.
    """
    return cls.KEYWORD + _SECTION_SUFFIX

  @property
  def datastore_client(self):
    """Getter for private |self._datastore_client| property."""
    if self._datastore_client is None:
      self._datastore_client = (
          datastore_client.LastExecutionRecordStore())

    return self._datastore_client

  @property
  def keyword(self):
    """Getter for private |self.KEYWORD| property."""
    return self.KEYWORD

  @property
  def launch_control_branch_targets(self):
    """Get a dict of branch:targets for launch controls from all tasks."""
    branches = {}
    for per_task in self.task_list:
      for branch in per_task.launch_control_branches:
        branches.setdefault(branch, []).extend(
            per_task.launch_control_targets)

    return branches
