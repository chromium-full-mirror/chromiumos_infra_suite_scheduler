# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for tot_manager unittests."""

import unittest

import mock
import tot_manager


class FakeTotMilestoneManager(tot_manager.TotMilestoneManager):

  def __init__(self, is_sanity):
    self.is_sanity = is_sanity
    self.storage_client = None
    self.tot = self._tot_milestone()


class TotMilestoneManagerTestCase(unittest.TestCase):

  def setUp(self):
    tot_patcher = mock.patch('tot_manager.TotMilestoneManager')
    self._mock_tot = tot_patcher.start()
    self.addCleanup(tot_patcher.stop)

    build_patcher = mock.patch('build_lib.get_latest_cros_build_from_gs')
    build_patcher.start().return_value = 'R56-abc-def'
    self.addCleanup(build_patcher.stop)

  def testTotManagerWithSanity(self):
    """Test TotManager's tot in sanity check."""
    self._mock_tot.return_value = FakeTotMilestoneManager(True)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertEqual(fake_tot_manager.tot, 'R40')

  def testTotManagerWithoutSanity(self):
    """Test TotManager's tot without sanity check."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertEqual(fake_tot_manager.tot, 'R56')

  def testConvertToT(self):
    """Test convert_tot_spec when given tot_spec is 'tot'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertEqual(fake_tot_manager.convert_tot_spec('tot'), 'R56')

  def testConvertToTMinus1(self):
    """Test convert_tot_spec when given tot_spec is 'tot-1'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertEqual(fake_tot_manager.convert_tot_spec('tot-1'), 'R55')

  def testConvertToTMinus2(self):
    """Test convert_tot_spec when given tot_spec is 'tot-2'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertEqual(fake_tot_manager.convert_tot_spec('tot-2'), 'R54')

  def testConvertToTMinus9(self):
    """Test convert_tot_spec when given tot_spec is 'tot-9'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertEqual(fake_tot_manager.convert_tot_spec('tot-9'), 'R47')

  def testConvertToTMinus10(self):
    """Test convert_tot_spec when given invalid tot_spec 'tot-10'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertRaises(ValueError, fake_tot_manager.convert_tot_spec, 'tot-10')

  def testConvertToTMinus0(self):
    """Test convert_tot_spec when given invalid tot_spec 'tot-0'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertRaises(ValueError, fake_tot_manager.convert_tot_spec, 'tot-0')

  def testConvertToTBadSpec(self):
    """Test convert_tot_spec when given tot_spec is unrecognized."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertRaises(ValueError,
                      fake_tot_manager.convert_tot_spec, 'bad_tot')

  def testCheckSpecsEqualToT(self):
    """Test check_branch_specs with branch_specs 'tot'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertTrue(
        tot_manager.check_branch_specs(['==tot'], fake_tot_manager))

  def testCheckSpecsLessThanToT(self):
    """Test check_branch_specs with branch_specs '<=tot-1'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertTrue(
        tot_manager.check_branch_specs(['<=tot-1'], fake_tot_manager))

  def testCheckSpecsMoreThanMilestone(self):
    """Test check_branch_specs with branch_specs '>=R56'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertTrue(
        tot_manager.check_branch_specs(['>=R56'], fake_tot_manager))

  def testCheckSpecsBareBranch(self):
    """Test check_branch_specs with branch_specs 'factory'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertTrue(
        tot_manager.check_branch_specs(['factory'], fake_tot_manager))

  def testCheckSpecsBadBranch(self):
    """Test check_branch_specs fails with branch_specs 'bad_branch'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertRaises(ValueError,
                      tot_manager.check_branch_specs,
                      ['bad_branch'],
                      fake_tot_manager)

  def testCheckSpecsBareBranchAndToT(self):
    """Test check_branch_specs with branch_specs 'factory,>=tot-1'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertTrue(
        tot_manager.check_branch_specs(['factory', '>=tot-1'],
                                       fake_tot_manager))

  def testCheckSpecsMoreThanOneNumeric(self):
    """Test check_branch_specs fails with branch_specs '==tot,>=tot-1'."""
    self._mock_tot.return_value = FakeTotMilestoneManager(False)
    fake_tot_manager = tot_manager.TotMilestoneManager()
    self.assertRaises(ValueError,
                      tot_manager.check_branch_specs,
                      ['==tot', '>=tot-1'],
                      fake_tot_manager)


if __name__ == '__main__':
  unittest.main()
