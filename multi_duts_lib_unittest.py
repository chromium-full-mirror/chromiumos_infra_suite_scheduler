# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for multi_duts_lib unittests."""


import unittest
import multi_duts_lib


class MultiDUTsLibTestCase(unittest.TestCase):

  def setUp(self):
    self.secondary_targets = [
      multi_duts_lib.BuildTarget(
        board="nami",
        model=None,
        cros_build="nami-release/R92-12000.00"
      ),
      multi_duts_lib.BuildTarget(
        board="coral",
        model="babytiger",
        cros_build="coral-release/R92-12000.00"
      )
    ]
    self.stringified_targets = "nami,,nami-release/R92-12000.00;coral,babytiger,coral-release/R92-12000.00"

  def testConvertSecondaryTargetsToString(self):
    """Test convert a list of BuildTarget to string format."""
    got = multi_duts_lib.convert_secondary_targets_to_string(self.secondary_targets)
    want = self.stringified_targets
    self.assertEqual(got, want)

  def testRestructSecondaryTargetsFromString(self):
    """Test restruct a list of BuildTarget from a string."""
    got = multi_duts_lib.restruct_secondary_targets_from_string(self.stringified_targets)
    want = self.secondary_targets
    self.assertEqual(got, want)
