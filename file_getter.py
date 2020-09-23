# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Module for fetching files used by suite scheduler."""

import logging
import os
import subprocess

# The path to save credentials.
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), 'credentials')

# The path to save configs.
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'configs')

# Suite scheduler event config file
SUITE_SCHEDULER_CONFIG_FILE = os.path.join(CONFIG_PATH, 'suite_scheduler.ini')

# The suite scheduler config file for testing.
TEST_SUITE_SCHEDULER_CONFIG_FILE = os.path.join(CONFIG_PATH,
                                                'fake_suite_scheduler.ini')

# Lab config file
LAB_CONFIG_FILE = os.path.join(CONFIG_PATH, 'lab_config.ini')

# Test lab config file
TEST_LAB_CONFIG_FILE = os.path.join(CONFIG_PATH, 'fake_lab_config.ini')

# Suite scheduler config repo
NEW_SUITE_SCHEDULER_CONFIG_FILE = None
NEW_LAB_CONFIG_FILE = None


def clone_config():
  """Function to clone the config for suite scheduler from the config-internal repo."""
  global NEW_SUITE_SCHEDULER_CONFIG_FILE
  global NEW_LAB_CONFIG_FILE
  temp_dir = '/tmp/config-internal'
  cmd = 'git clone --depth 1 https://chrome-internal.googlesource.com/chromeos/config-internal {}'.format(
      temp_dir)
  logging.info('Cloning internal config repo.')
  if (NEW_SUITE_SCHEDULER_CONFIG_FILE is None or NEW_LAB_CONFIG_FILE is None):
    try:
      stdout = subprocess.check_output([cmd], shell=True)
      logging.info(stdout)
      suite_scheduler_path = os.path.join(temp_dir, 'test', 'suite_scheduler',
                                          'generated')
      NEW_SUITE_SCHEDULER_CONFIG_FILE = os.path.join(suite_scheduler_path,
                                                     'suite_scheduler.ini')
      NEW_LAB_CONFIG_FILE = os.path.join(suite_scheduler_path,
                                         'lab_config.ini')
      if not os.path.exists(NEW_SUITE_SCHEDULER_CONFIG_FILE):
        logging.error('suite_scheduler.ini does not exist.')
      if not os.path.exists(NEW_LAB_CONFIG_FILE):
        logging.error('lab_config.ini does not exist.')
    except Exception as e:
      logging.error(str(e))

# Service account secret json file used for staging project.
STAGING_CLIENT_SECRETS_FILE = os.path.join(
    CREDENTIALS_PATH,
    'suite-scheduler-staging_client_secret_service_account.json')

# Service account secret json file used for prod project.
PROD_CLIENT_SECRETS_FILE = os.path.join(
    CREDENTIALS_PATH, 'suite-scheduler_client_secret_service_account.json')
