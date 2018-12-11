# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module of TimedEvent, triggered by time points."""

import datetime
import logging

import base_event
import constants
import global_config
import time_converter


class TimedEvent(base_event.BaseEvent):
  """Base class for events that triggered based on time."""

  def __init__(self, event_settings, last_exec_utc, target_exec_utc):
    """Initialize a TimedEvent.

    Args:
      event_settings: a config_reader.EventSettings object, indicating
        the event settings.
      last_exec_utc: The utc datetime.datetime timestamp of last
        execution.
      target_exec_utc: The utc datetime.datetime timestamp of the expected
        execution for current round.
    """
    super(TimedEvent, self).__init__(
        event_settings, last_exec_utc, target_exec_utc)
    self.since_date = self.target_exec_utc - datetime.timedelta(
        days=self.DAYS_INTERVAL)

  def set_default_utc_time(self):
    """Convert default day/hour to UTC for TimedEvent."""
    default_pst_timeinfo = time_converter.convert_time_info(
        time_converter.TimeInfo(self.DEFAULT_PST_DAY,
                                self.DEFAULT_PST_HOUR))
    self._default_utc_day = default_pst_timeinfo.weekday
    self._default_utc_hour = default_pst_timeinfo.hour


class Nightly(TimedEvent):
  """The class for nightly-triggered TimedEvent.

  A nightly-triggered TimedEvent allows a task to be triggered at
  every day. One can set the hour when this task should be triggered
  through 'hour' setting.

  For example:
  [AVWebcam]
  run_on: nightly
  hour: 19
  This nightly task means it should be triggered at 19:00 everyday.
  """
  KEYWORD = 'nightly'
  PRIORITY = constants.Priorities.DAILY

  # Each task may have its own setting of 'hour'. The default is set to 9PM.
  # Nightly task cannot set 'day'. The default is None.
  DEFAULT_PST_DAY = None
  DEFAULT_PST_HOUR = 21

  # Nightly event is triggered once a day.
  DAYS_INTERVAL = 1

  # Every 1 hours a batch of tasks in task_list of nightly event is
  # scheduled, eg. suite scheduler will schedule all nightly event's
  # tasks whose hour is set 4 in its first run after 4:00am every day.
  LAST_EXEC_INTERVAL = 1

  # Kicked off once a day, so nightly event's tasks get the full day to run
  TIMEOUT = 24

  def __init__(self, event_settings, last_exec_utc):
    """Initialize a nightly TimedEvent.

    Args:
      event_settings: a config_reader.EventSettings object.
      last_exec_utc: The utc datetime.datetime timestamp of last
          execution.
    """
    self.set_default_utc_time()
    now = time_converter.utc_now()
    target_exec_utc = datetime.datetime(
        now.year, now.month, now.day, now.hour,
        tzinfo=time_converter.UTC_TZ)

    super(Nightly, self).__init__(
        event_settings, last_exec_utc, target_exec_utc)

  def set_task_list(self, task_list):
    """Set task list for nightly event.

    This also update all tasks' time from PST to UTC.

    Args:
      task_list: the given list of task.Task objects, in which their
        day and hour are in PST.
    """
    for per_task in task_list:
      hour = self.DEFAULT_PST_HOUR if per_task.hour is None else per_task.hour
      utc_time_info = time_converter.convert_time_info(
          time_converter.TimeInfo(per_task.day, hour))
      per_task.hour = utc_time_info.hour
      per_task.day = utc_time_info.weekday

    self.task_list = list(task_list)

  def filter_tasks(self):
    """Filter tasks by target_exec_utc."""
    if global_config.GAE_TESTING:
      super(Nightly, self).filter_tasks()
    else:
      cur_hour = self.target_exec_utc.hour
      logging.debug('Current hour for %s event: %s', self.keyword, cur_hour)
      tasks = [t for t in self.task_list
               if ((t.hour is not None and cur_hour == t.hour) or
                   (t.hour is None and cur_hour == self._default_utc_hour))]
      self.task_list = tasks


class Weekly(TimedEvent):
  """The class for weekly-triggered TimedEvent.

  A weekly-triggered TimedEvent allows a task to be triggered at
  every week. One can set the day when this task should be triggered
  through 'day' setting, and set the hour for tasks to run by config
  section in 'weekly_params'.

  For example:
  [ChameleonDpOldBranch]
  run_on: weekly
  day: 5
  This weekly task means it should be triggered at every Saturday 11PM, which
  is the default PST hour setting (DEFAULT_PST_HOUR) for Weekly Event.
  """
  KEYWORD = 'weekly'
  PRIORITY = constants.Priorities.WEEKLY

  # Each task may have its own settings of 'day' & 'hour'. The default day
  # is Saturday. The default hour is set to 11PM.
  DEFAULT_PST_DAY = 5  # Saturday
  DEFAULT_PST_HOUR = 23

  # Weekly event is triggered once a week.
  DAYS_INTERVAL = 7

  # Every 24 hours a batch of tasks in task_list of weekly event is
  # scheduled, eg. suite scheduler will schedule all weekly event's
  # tasks whose day is set 5 in its first run after 11PM every Saturday.
  LAST_EXEC_INTERVAL = 24

  # Kicked off once a week, so weekly event's tasks get the 7 days to run
  TIMEOUT = 7 * 24

  def __init__(self, event_settings, last_exec_utc):
    """Initialize a weekly TimedEvent.

    Args:
      event_settings: A config_reader.EventSettings object.
      last_exec_utc: The utc datetime.datetime timestamp of last
        execution.
    """
    self.set_default_utc_time()
    now = time_converter.utc_now()

    self.event_hour_pst = event_settings.event_hour
    if self.event_hour_pst is None:
      self.event_hour_pst = self.DEFAULT_PST_HOUR

    target_exec_utc = datetime.datetime(
        now.year, now.month, now.day, now.hour,
        tzinfo=time_converter.UTC_TZ)

    super(Weekly, self).__init__(
        event_settings, last_exec_utc, target_exec_utc)

  def set_task_list(self, task_list):
    """Set task list for weekly event.

    This also update all tasks' time from PST to UTC.

    Args:
      task_list: the given list of task.Task objects, in which their
        day and hour are in PST.
    """
    for per_task in task_list:
      hour = self.event_hour_pst if per_task.hour is None else per_task.hour
      day = self.DEFAULT_PST_DAY if per_task.day is None else per_task.day
      utc_time_info = time_converter.convert_time_info(
          time_converter.TimeInfo(day, hour))
      per_task.hour = utc_time_info.hour
      per_task.day = utc_time_info.weekday

    self.task_list = list(task_list)

  def filter_tasks(self):
    """Filter tasks by target_exec_utc."""
    if global_config.GAE_TESTING:
      super(Weekly, self).filter_tasks()
    else:
      cur_day = self.target_exec_utc.weekday()
      cur_hour = self.target_exec_utc.hour
      logging.debug('Current weekday for %s event: %s', self.keyword, cur_day)
      logging.debug('Current hour for %s event: %s', self.keyword, cur_hour)
      tasks = [t for t in self.task_list if
               (t.day == cur_day and t.hour == cur_hour)]
      self.task_list = tasks
