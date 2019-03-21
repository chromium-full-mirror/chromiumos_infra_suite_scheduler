# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for skylab-related logic."""

import logging

import config_reader


def _read_migration_configs(migration_config):
  """Read configs from migration config file.

  Args:
    migration_config: A config_reader.MigrationConfig object.

  Returns:
    A dict of skylab migration configs of suites.
  """
  skylab_suites = (migration_config.get_skylab_suites_dump()
                   if migration_config else [])
  logging.info('Skylab suites: %r', skylab_suites)
  return skylab_suites


def should_run_in_skylab(migration_config, board, model, suite, pool):
  """Check whether a suite task should be run in skylab.

  Args:
    migration_config: A config_reader.MigrationConfig object.
    board: A string board name.
    model: A string model name.
    suite: A string suite name.
    pool: A string pool name.

  Returns:
    A boolean variable to indicate whether a suite task should be run in skylab.
  """
  # We're using link to drive skylab suites green. See crbug/922350
  if board == 'link':
    return True

  skylab_suites = _read_migration_configs(migration_config)

  sk = config_reader.suite_key(suite)
  pk = config_reader.pool_key(pool)
  if sk not in skylab_suites:
    return False

  if pk not in skylab_suites[sk]:
    return False

  if model is None:
    return config_reader.model_key(board) in skylab_suites[sk][pk]
  else:
    return config_reader.model_key(model) in skylab_suites[sk][pk]
