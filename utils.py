# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for use by any callers."""

import logging

import time


DEFAULT_TIMEOUT_SEC = 10


def wait_for_value(func, expected_value=None, exception_to_raise=(),
                   timeout_sec=DEFAULT_TIMEOUT_SEC):
  """Wait to return the value of func().

  If |expected_value| is not set, return immediately.

  If |expected_value| is set, polls the return value until |expected_value|
  is reached, and returns that value.

  Polling will stop after |timeout_sec| regardless of these thresholds.

  Args:
    func: function whose return value is to be waited on.
    expected_value: wait for func to return this value.
    exception_to_raise: exceptions that func() could raise.
    timeout_sec: Number of seconds to wait before giving up and
      returning whatever value func() last returned.

  Returns:
    The most recent return value of func().

  Raises:
    Unexpected exceptions: not exist in exception_to_raise.
  """
  value = None
  start_time_sec = time.time()
  while True:
    time.sleep(0.1)
    try:
      value = func()
      if (expected_value is None or
          (expected_value is not None and value == expected_value)):
        break

      if time.time() - start_time_sec >= timeout_sec:
        break
    except exception_to_raise as e:
      logging.warning(str(e))

  return value
