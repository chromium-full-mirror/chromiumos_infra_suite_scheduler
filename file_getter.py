# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Module for fetching files used by suite scheduler."""

import base64
import logging
import os
import subprocess
import urllib2

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
  """Function to clone the config for suite scheduler from the current head."""
  global NEW_SUITE_SCHEDULER_CONFIG_FILE
  global NEW_LAB_CONFIG_FILE
  logging.info('Fetching config from suite scheduler repo.')
  if (NEW_SUITE_SCHEDULER_CONFIG_FILE is None or NEW_LAB_CONFIG_FILE is None):
    try:
      suite_scheduler_response = urllib2.urlopen(
          'https://chromium.googlesource.com/chromiumos/infra/suite_scheduler/+/refs/heads/master/generated_configs/suite_scheduler.ini?format=text'
      )
      suite_scheduler_html = suite_scheduler_response.read()
      NEW_SUITE_SCHEDULER_CONFIG_FILE = base64.b64decode(suite_scheduler_html)
      lab_config_response = urllib2.urlopen(
          'https://chromium.googlesource.com/chromiumos/infra/suite_scheduler/+/refs/heads/master/generated_configs/lab_config.ini?format=text'
      )
      lab_config_html = lab_config_response.read()
      NEW_LAB_CONFIG_FILE = base64.b64decode(lab_config_html)
    except Exception as e:
      logging.error(str(e))

# Service account secret json file used for staging project.
STAGING_CLIENT_SECRETS_FILE = os.path.join(
    CREDENTIALS_PATH,
    'suite-scheduler-staging_client_secret_service_account.json')

# Service account secret json file used for prod project.
PROD_CLIENT_SECRETS_FILE = os.path.join(
    CREDENTIALS_PATH, 'suite-scheduler_client_secret_service_account.json')
