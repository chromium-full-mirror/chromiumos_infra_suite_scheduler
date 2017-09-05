# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for utils unittests."""

import unittest

import utils


# Gloabl variable for mocking functions.
SUCCESS_COUNT = 0


def successful_func():
  """Mock a successful function with clear returns."""
  return 1


def failed_func():
  """Mock a failed function which raises error."""
  raise ValueError('')


def half_func():
  """Mock a function first raises error, then succeeds."""
  global SUCCESS_COUNT
  SUCCESS_COUNT += 1

  if SUCCESS_COUNT >= 10:
    return successful_func()
  else:
    failed_func()


class UtilsTestCase(unittest.TestCase):

  def setUp(self):
    """Reset global variable SUCCESS_COUNT."""
    global SUCCESS_COUNT
    SUCCESS_COUNT = 0

  def testWaitForValueWithExpectedValueSuccess(self):
    """Test wait_for_value with right expected_value."""
    self.assertEqual(
        utils.wait_for_value(successful_func, expected_value=1), 1)

  def testWaitForValueWithExpectedValueFailure(self):
    """Test wait_for_value with wrong expected_value."""
    self.assertEqual(
        utils.wait_for_value(successful_func, expected_value=2, timeout_sec=1),
        1)

  def testWaitForValueWithoutExpectedValueSuccess(self):
    """Test wait_for_value with empty expected_value."""
    self.assertEqual(utils.wait_for_value(successful_func), 1)

  def testWaitForValueWithEmptyException(self):
    """Test wait_for_value with empty exception_to_raise."""
    self.assertRaises(ValueError, utils.wait_for_value, failed_func)

  def testWaitForValueWithRightException(self):
    """Test wait_for_value with right exception_to_raise."""
    self.assertEqual(
        utils.wait_for_value(half_func, exception_to_raise=ValueError), 1)

  def testWaitForValueWithMultipleException(self):
    """Test wait_for_value with multiple exception_to_raise."""
    self.assertEqual(
        utils.wait_for_value(half_func,
                             exception_to_raise=(ValueError, KeyError)), 1)

  def testWaitForValueWithWrongException(self):
    """Test wait_for_value with wrong exception_to_raise."""
    self.assertRaises(ValueError, utils.wait_for_value,
                      half_func, exception_to_raise=KeyError)
