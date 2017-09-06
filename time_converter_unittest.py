# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for time_converter unittests."""

import datetime
import unittest

import mock
import pytz

import time_converter


# datetime.datetime cannot be patched directly since it's a built-in
# type that is immutable. NewDatetime is created here for patching
# datetime.datetime.now.
class NewDatetime(datetime.datetime):

  @classmethod
  def now(cls):
    pass


class TimeConverterTestCase(unittest.TestCase):

  def setUp(self):
    old_datetime = datetime.datetime
    datetime.datetime = NewDatetime
    mock_now = mock.patch('datetime.datetime.now')
    self._mock_now = mock_now.start()
    self.addCleanup(mock_now.stop)
    self.addCleanup(setattr, datetime, 'datetime', old_datetime)

  def testConvertPSTToUTC(self):
    """Convert a task on Saturday 9:00 on at day PST (2017, 8, 1).

    PST (2017, 8, 1, 9) should be converted to UTC (2017, 8, 1, 16).
    The task should be run at Saturday 16:00 in UTC.
    """
    self._mock_now.return_value = datetime.datetime(2017, 8, 1)
    pst_time = time_converter.TimeInfo(5, 9)
    utc_time = time_converter.convert_time_info_to_utc(pst_time)
    self.assertEqual(utc_time.weekday, 5)
    self.assertEqual(utc_time.hour, 16)

  def testConvertPSTToUTCNextDay(self):
    """Convert a task on Saturday 19:00 at day PST (201# 7, 8, 1).

    PST (2017, 8, 1, 19) should be converted to UTC (20# 17, 8, 2, 2).
    The task should be run at Sunday 2:00 in UTC.
    """
    self._mock_now.return_value = datetime.datetime(2017, 8, 1)
    pst_time = time_converter.TimeInfo(5, 19)
    utc_time = time_converter.convert_time_info_to_utc(pst_time)
    self.assertEqual(utc_time.weekday, 6)
    self.assertEqual(utc_time.hour, 2)

  def testConvertPSTToUTCNextMonday(self):
    """Convert a task on Sunday 19:00 at day PST (2017,#  8, 1).

    PST (2017, 8, 1, 9) should be converted to UTC (201# 7, 8, 1, 16).
    The task should be run at Monday 2:00 in UTC.
    """
    self._mock_now.return_value = datetime.datetime(2017, 8, 1)
    pst_time = time_converter.TimeInfo(6, 19)
    utc_time = time_converter.convert_time_info_to_utc(pst_time)
    self.assertEqual(utc_time.weekday, 0)
    self.assertEqual(utc_time.hour, 2)

  def testConvertPSTToUTCWinterTime(self):
    """Convert a task on Saturday 9:00 at day PST (2017# , 2, 1).

    PST (2017, 2, 1, 9) should be converted to UTC (201# 7, 2, 1, 17).
    The task should be run at Saturday 17:00 in UTC.
    """
    self._mock_now.return_value = datetime.datetime(2017, 2, 1)
    pst_time = time_converter.TimeInfo(5, 9)
    utc_time = time_converter.convert_time_info_to_utc(pst_time)
    self.assertEqual(utc_time.weekday, 5)
    self.assertEqual(utc_time.hour, 17)

  def testConvertHKToUTC(self):
    """Convert a task on Saturday 9:00 at day Asia/HK (# 2017, 8, 1).

    Asia/HK (2017, 8, 1, 9) should be converted to UTC (201# 7, 8, 1, 1).
    The task should be run at Saturday 1:00 in UTC.
    """
    self._mock_now.return_value = datetime.datetime(2017, 8, 1)
    hk_time = time_converter.TimeInfo(5, 9)
    utc_time = time_converter.convert_time_info_to_utc(
        hk_time, source_tz=pytz.timezone('Asia/Hong_Kong'))
    self.assertEqual(utc_time.weekday, 5)
    self.assertEqual(utc_time.hour, 1)

  def testConvertHKToUTCPreviousDay(self):
    """Convert a task on Saturday 2:00 at day Asia/HK (# 2017, 8, 1).

    Asia/HK (2017, 8, 1, 2) should be converted to UTC (201# 7, 7, 31, 18).
    The task should be run at Friday 18:00 in UTC.
    """
    self._mock_now.return_value = datetime.datetime(2017, 8, 1)
    hk_time = time_converter.TimeInfo(5, 2)
    utc_time = time_converter.convert_time_info_to_utc(
        hk_time, source_tz=pytz.timezone('Asia/Hong_Kong'))
    self.assertEqual(utc_time.weekday, 4)
    self.assertEqual(utc_time.hour, 18)


if __name__ == '__main__':
  unittest.main()
