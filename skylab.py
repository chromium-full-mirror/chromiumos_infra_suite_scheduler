# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for skylab-related logic."""


def should_run_in_skylab(board, model, suite,
                         skylab_boards, skylab_models, skylab_suites):
  """Check whether a suite task should be run in skylab.

  Args:
    board: A string board name.
    model: A string model name.
    suite: A string suite name.
    skylab_boards: A list of boards that should be run in skylab.
    skylab_models: A map of models that should be run in skylab.
    skylab_suites: A list of suites that should be run in skylab.

  Returns:
    A boolean variable to indicate whether a suite task should be run in skylab.
  """
  # We're using link to drive skylab suites green. See crbug/922350
  if board == 'link':
    return True

  if suite not in skylab_suites:
    return False

  if model is None:
    return board in skylab_boards
  else:
    return model in skylab_models.get(board, [])
