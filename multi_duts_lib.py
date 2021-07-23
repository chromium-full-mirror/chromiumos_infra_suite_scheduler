# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for multi-DUTs support related helpers."""

from collections import namedtuple

# BuildTarget contains information for a hwtest target.
BuildTarget = namedtuple('BuildTarget', ['board', 'model', 'cros_build'])


def convert_secondary_targets_to_string(secondary_targets):
  """Convert A list of BuildTarget namedtuple to a string.

  Args:
    secondary_targets: a list of BuildTarget namedtuple. Example:
      [
        BuildTarget(
          board="nami",
          model=None,
          cros_build="nami-release/R88-12000.00"
        ),
        BuildTarget(
          board="coral",
          model="babytiger",
          cros_build="coral-release/R85-11000.00"
        )
      ]

  Returns:
    A string which BuildTargets are separated by ";" while attribute
    of a BuildTarget are separated by ",". Example:
    "nami,,nami-release/R88-12000.00;coral,babytiger,coral-release/R85-11000.00"
  """
  l = []
  for target in secondary_targets:
    board = target.board or ''
    model = target.model or ''
    cros_build = target.cros_build or ''
    l.append('%s,%s,%s' % (board, model, cros_build))
  return ';'.join(l)


def restruct_secondary_targets_from_string(input_string):
  """Restruct a stringified secondary targets list.

  Args:
    input_string: a output from convert_secondary_targets_to_string function.

  Returns:
    a list of BuildTarget namedtuple.
  """
  secondary_targets = []
  if not input_string:
      return secondary_targets
  for section in input_string.split(';'):
    board, model, cros_build = section.split(',')
    board = board or None
    model = model or None
    cros_build = cros_build or None
    secondary_targets.append(
      BuildTarget(board=board, model=model, cros_build=cros_build))
  return secondary_targets
