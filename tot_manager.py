# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for CrOS ToT manager."""

import re

import build_lib
import constants
import rest_client


def check_branch_specs(branch_specs, tot_manager):
  """Make sure entries in the branch_specs list are correctly formed.

  It accepts any of BARE_BRANCHES in |branch_specs|, one numeric string of
  the form '>=RXX' or '==RXX', where 'RXX' is a CrOS milestone number, or
  one numeric string of the form '**tot**', like '>=tot-2'.

  Args:
    branch_specs: an iterable of branch specifiers, like ['>=tot-1'].
    tot_manager: a TotMilestoneManager to convert tot string.

  Returns:
    True if branch_specs check is passed.

  Raises:
    ValueError: when parsing non-valid branch_spec or there're more than one
      numeric string in branch_specs.
  """
  only_one_numeric_constraint = False
  for branch in branch_specs:
    if branch in build_lib.BARE_BRANCHES:
      continue

    if not only_one_numeric_constraint:
      # '<=' is dropped
      if branch.startswith('>=R') or branch.startswith('==R'):
        only_one_numeric_constraint = True
      elif 'tot' in branch:
        tot_manager.convert_tot_spec(branch[branch.index('tot'):])
        only_one_numeric_constraint = True

      if only_one_numeric_constraint:
        continue

    raise ValueError("%s isn't a valid branch spec." % branch)

  return True


class TotMilestoneManager(object):
  """A class capable of converting tot string to milestone numbers.

  This class is used as a cache for the tot milestone, so we don't
  repeatedly hit google storage for all O(100) tasks in suite
  scheduler's ini file.
  """

  def __init__(self, is_sanity=False):
    """Initialize a manager for getting/calculating the Tot milestone.

    Args:
      is_sanity: True if suite_scheduler is running for sanity check.
        When it's set to True, the code won't make gsutil call to
        get the actual tot milestone to avoid dependency on the
        installation of gsutil to run sanity check. By default it's
        False.
    """
    self.is_sanity = is_sanity
    if not self.is_sanity:
      self.storage_client = rest_client.StorageRestClient(
          rest_client.BaseRestClient(
              constants.RestClient.STORAGE_CLIENT.scopes,
              constants.RestClient.STORAGE_CLIENT.service_name,
              constants.RestClient.STORAGE_CLIENT.service_version))
    self.tot = self._tot_milestone()

  def convert_tot_spec(self, tot_spec):
    """Convert a tot spec to the appropriate milestone.

    The valid lag number scope is [1,9].
    Assume tot is R40:
    tot   -> R40
    tot-1 -> R39
    tot-2 -> R38
    ...
    tot-9 -> R31
    tot-(any other numbers) -> Raise a ValueError.

    With the last option one assumes that a malformed configuration
    that has 'tot' in it, wants at least tot.

    Args:
      tot_spec: A string representing the tot spec.

    Returns:
      A milestone string, like 'R40'.

    Raises:
      ValueError: If the tot_spec doesn't match the expected format.
    """
    tot_spec = tot_spec.lower()
    match = re.match('(tot)[-]?([1-9]?)$', tot_spec)
    if not match:
      raise ValueError('%s is not a valid branch spec.' % tot_spec)

    tot_mstone = self.tot
    num_back = match.groups()[1]
    if num_back:
      tot_mstone_num = tot_mstone.lstrip('R')
      effective_milestone = int(tot_mstone_num) - int(num_back)
      # R95 doesn't exist. Use this ugly hack to correct for the right milestone.
      # The second logic clause gets around unittests :)
      if effective_milestone <= 95 and int(tot_mstone_num) > 95:
        effective_milestone -= 1

      tot_mstone = tot_mstone.replace(
          tot_mstone_num, str(effective_milestone))

    return tot_mstone

  def _tot_milestone(self):
    """Get the tot milestone, eg: R40.

    Returns:
      A string representing the Tot milestone.

    Raises:
      build_lib.NoBuildError: if no milestone is found.
    """
    if self.is_sanity:
      return 'R40'

    response = build_lib.get_latest_cros_build_from_gs(
        self.storage_client)
    return response.split('-')[0]
