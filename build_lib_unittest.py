# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for build_lib unittests."""

import unittest

import build_lib


class BuildLibTestCase(unittest.TestCase):

  def testReshapeBoard(self):
    self.assertEqual(build_lib.reshape_board('samus-kernelnext'), 'samus')
    self.assertEqual(build_lib.reshape_board('eve-arcvm'), 'eve')
    self.assertEqual(build_lib.reshape_board('kukui-arc-r'), 'kukui')
    self.assertEqual(build_lib.reshape_board('hatch-arc-r-userdebug'), 'hatch')
    self.assertEqual(build_lib.reshape_board('octopus'), 'octopus')

if __name__ == '__main__':
  unittest.main()
