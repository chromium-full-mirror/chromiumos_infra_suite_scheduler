# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The module contains time-related utility functions.

Please note that suite scheduler use UTC timezone to log/kick off tests.
"""

import collections
import datetime
import pytz

# The format of time string.
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# The format to print a timestamp.
STR_TIME_FORMAT = '%Y-%m-%d %H:%M:%S %Z'

# The format for calendar timestamp.
CALENDAR_TIME_FORMAT = '%Y-%m-%dT%H:%M:%S'

# The format for stackdriver logging timestamp.
STACKDRIVER_TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

UTC_TZ = pytz.utc
PST_TZ = pytz.timezone('America/Los_Angeles')

TimeInfo = collections.namedtuple(
    'TimeInfo',
    [
        'weekday',
        'hour',
    ])


def utc_now():
  """Return now() in UTC timezone.

  Returns:
      a datetime.datetime object representing utc now().
  """
  return datetime.datetime.now(UTC_TZ)


def pst_now():
  """Return now() in PST timezone.

  Returns:
      a datetime.datetime object representing pst now().
  """
  return datetime.datetime.now(PST_TZ)


def convert_time_info(time_info, source_tz=PST_TZ, target_tz=UTC_TZ):
  """Convert (day, hour) extracted from config file to UTC timezone.

  The time_info could be in any timezone, which is indicated by source_tz.

  Args:
      time_info: a TimeInfo object including weekday & hour. Weekday is 0~6,
          hour is 0~23.
      source_tz: a pytz timezone object, specifies the original timezone to
          be converted. Default is PST.
      target_tz: a pytz timezone object, specifies the target timezone to be
          be converted to. Default is UTC.

  Returns:
      A UTC TimeInfo object.
  """
  source_now = datetime.datetime.now(source_tz)
  utc_time = source_tz.localize(
      datetime.datetime(source_now.year, source_now.month,
                        source_now.day, time_info.hour)).astimezone(target_tz)
  weekday = time_info.weekday
  if weekday is not None and utc_time.weekday() != source_now.weekday():
    weekday = (weekday + utc_time.weekday() - source_now.weekday()) % 7

  return TimeInfo(weekday, utc_time.hour)
