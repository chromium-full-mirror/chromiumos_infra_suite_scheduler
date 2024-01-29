# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from retry import retry


class TestRetryDecorator(unittest.TestCase):

  def test_retry_success(self):
    @retry(max_retries=3)
    def to_be_decorated(message):
      return message

    expect = "original message"
    actual = to_be_decorated(expect)
    self.assertEqual(expect, actual)

  def test_retry_all_failures(self):
    @retry(max_retries=2, first_retry_delay_in_seconds=0.1, backoff=1.1)
    def to_be_decorated():
      raise Exception("error")

    with self.assertRaises(Exception):
      to_be_decorated()

  def test_retry_failure_then_success(self):
    store = {"count": 0}

    @retry(max_retries=2, first_retry_delay_in_seconds=0.1, backoff=1.1)
    def to_be_decorated():
      if store["count"] <= 0:
        store["count"] += 1
        raise Exception("error")
      return store["count"]

    expect = 1
    actual = to_be_decorated()
    self.assertEqual(expect, actual)


if __name__ == '__main__':
  unittest.main()
