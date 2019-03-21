# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for skylab-related logic."""

import logging


def _read_migration_configs(migration_config):
  """Read configs from migration config file.

  Args:
    migration_config: A config_reader.MigrationConfig object.

  Returns:
    A tuple of (models, suites) allowed in skylab.
  """
  skylab_suites = (migration_config.get_skylab_suite_list()
                   if migration_config else [])
  skylab_models = (migration_config.get_skylab_model_list()
                   if migration_config else {})
  logging.info('Skylab models: %r', skylab_models)
  logging.info('Skylab suites: %r', skylab_suites)
  return skylab_models, skylab_suites


def should_run_in_skylab(migration_config, board, model, suite):
  """Check whether a suite task should be run in skylab.

  Args:
    migration_config: A config_reader.MigrationConfig object.
    board: A string board name.
    model: A string model name.
    suite: A string suite name.

  Returns:
    A boolean variable to indicate whether a suite task should be run in skylab.
  """
  # We're using link to drive skylab suites green. See crbug/922350
  if board == 'link':
    return True

  skylab_models, skylab_suites = _read_migration_configs(
      migration_config)

  if suite not in skylab_suites:
    return False

  if model is None:
    return board in skylab_models
  else:
    return model in skylab_models
