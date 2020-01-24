# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for ChromeOS build utils without import external packages."""

import logging


def parse_full_model(full_model):
  """Parse full model name to single board and model.

  Args:
    full_model: A string, whose format is like 'board_model or
                family_board_model'.

  Returns:
    A tuple (board, model).

  Raises:
    ValueError if the full_model is in wrong format.
  """
  model_tokens = full_model.strip().split('_')
  if len(model_tokens) == 2:
    return model_tokens[0], model_tokens[1]
  if len(model_tokens) == 3:
    return '_'.join(model_tokens[:2]), model_tokens[2]

  logging.error('Invalid full_model format: %s', full_model)
  raise ValueError
