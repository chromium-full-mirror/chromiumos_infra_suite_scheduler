# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module of BuildEvent, triggerred by new builds."""

import datetime

import base_event
import constants
import time_converter


class NewBuild(base_event.BaseEvent):
  """The class for BuildEvent triggerred by new builds."""

  KEYWORD = 'new_build'
  PRIORITY = constants.Priorities.POSTBUILD

  # Every several hours a batch of tasks in task_list of NewBuild event
  # is scheduled. Here we set the LAST_EXEC_INTERVAL=6.
  LAST_EXEC_INTERVAL = 6

  # NewBuild event's tasks get 12 hours to run, as builds come out
  # every 6 hours.
  TIMEOUT = 12

  def __init__(self, event_settings, last_exec_utc):
    """Initialize a BuildEvent.

    Args:
      event_settings: a config_reader.EventSettings object.
      last_exec_utc: The utc datetime.datetime timestamp of last
        execution.
    """
    now = time_converter.utc_now()
    target_exec_utc = datetime.datetime(
        now.year, now.month, now.day, now.hour, now.minute,
        tzinfo=time_converter.UTC_TZ)

    super(NewBuild, self).__init__(
        event_settings, last_exec_utc, target_exec_utc)

    self.since_date = self.last_exec_utc
