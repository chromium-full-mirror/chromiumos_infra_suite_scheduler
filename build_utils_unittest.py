# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for build_utils unittests."""

import unittest

import build_utils


class BuildUtilsTestCase(unittest.TestCase):

  def testParseNormalModelName(self):
    full_model = 'board_model'
    board = 'board'
    model = 'model'
    self.assertEqual(build_utils.parse_full_model(full_model), (board, model))

  def testParseModelNameWithFamilyModel(self):
    full_model = 'family_board_family_model'
    board = 'family_board'
    model = 'family_model'
    self.assertEqual(build_utils.parse_full_model(full_model), (board, model))

  def testParseInvalidFullModelRaisesException(self):
    invalid_full_models = ['atlas',
                           'family_board_model',
                           'too_long_name_a_name']
    for invalid_model in invalid_full_models:
      self.assertRaises(ValueError, build_utils.parse_full_model, invalid_model)

if __name__ == '__main__':
  unittest.main()
