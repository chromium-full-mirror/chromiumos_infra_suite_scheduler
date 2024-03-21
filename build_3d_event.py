# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module of BuildEvent, triggered by new builds."""

import datetime

import base_event
import constants
import time_converter


class NewBuild3D(base_event.BaseEvent):
  """The class for 3DBuildEvent triggered by completion of all new builds."""

  KEYWORD = 'new_build_3D'
  PRIORITY = constants.Priorities.NEWBUILD3D

  # Same as NewBuild, this config will not be picked by Suite scheduler
  LAST_EXEC_INTERVAL = 6

  # Same as NewBuild, this config will not be picked by Suite scheduler
  TIMEOUT = 12

  def __init__(self, event_settings, last_exec_utc):
    """Initialize a 3DBuildEvent.

    Args:
      event_settings: a config_reader.EventSettings object.
      last_exec_utc: The utc datetime.datetime timestamp of last
        execution.
    """
    now = time_converter.utc_now()
    target_exec_utc = datetime.datetime(
        now.year, now.month, now.day, now.hour, now.minute,
        tzinfo=time_converter.UTC_TZ)

    super(NewBuild3D, self).__init__(
        event_settings, last_exec_utc, target_exec_utc)

    self.since_date = self.last_exec_utc
