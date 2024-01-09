# Copyright 2017 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Module for fetching files used by suite scheduler."""

import base64
import constants
import logging
import os
import urllib2

from retry import retry
import utils

from oauth2client.contrib import appengine
from oauth2client.service_account import ServiceAccountCredentials

# The path to save credentials.
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), 'credentials')

# The path to save configs.
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'configs')

# The suite scheduler config file for testing.
TEST_SUITE_SCHEDULER_CONFIG_FILE = os.path.join(CONFIG_PATH,
                                                'fake_suite_scheduler.ini')

# Test lab config file
TEST_LAB_CONFIG_FILE = os.path.join(CONFIG_PATH, 'fake_lab_config.ini')

# Suite scheduler config repo
NEW_SUITE_SCHEDULER_CONFIG_FILE = None
NEW_LAB_CONFIG_FILE = None


@retry(max_retries=5, first_retry_delay_in_seconds=5)
def _write_internal_config(config_name):
  request = urllib2.Request('https://chrome-internal.googlesource.com/chromeos/config-internal/+/refs/heads/main/test/suite_scheduler/generated/{}?format=text'.format(config_name))

  # Add the OAuth2 headers to the request
  credentials = _get_credentials()
  access_token=credentials.get_access_token()
  request.add_header('Authorization', 'Bearer ' + access_token.access_token)

  tot_response = urllib2.urlopen(request).read()
  config_text = base64.b64decode(tot_response)
  # logging.info("got resp: %s", config_text)
  # NOTE: Logging removed due to LogExplorer limitations.

  dirname = "/tmp"
  utils.writedirs(dirname)

  filename = '{}/{}'.format(dirname, config_name)
  with open(filename, 'w') as f:
    f.write(config_text)
  return filename


def _get_credentials():
  # This applies to any AppEngine environment.
  if constants.environment() == constants.RunningEnv.ENV_PROD:
    return appengine.AppAssertionCredentials(["https://www.googleapis.com/auth/gerritcodereview"])
  else:
    return ServiceAccountCredentials.from_json_keyfile_name(STAGING_CLIENT_SECRETS_FILE, scopes=["https://www.googleapis.com/auth/gerritcodereview"])


def clone_config():
  """Function to clone the config for suite scheduler from the current head."""
  global NEW_SUITE_SCHEDULER_CONFIG_FILE
  global NEW_LAB_CONFIG_FILE
  logging.info('Fetching suite configs from suite scheduler repo.')
  try:
    NEW_SUITE_SCHEDULER_CONFIG_FILE = _write_internal_config('suite_scheduler.ini')
  except Exception as e:
    logging.error(str(e))

  logging.info('Fetching lab configs from suite scheduler repo.')
  try:
    NEW_LAB_CONFIG_FILE = _write_internal_config('lab_config.ini')
  except Exception as e:
    logging.error(str(e))


# Service account secret json file used for staging project.
STAGING_CLIENT_SECRETS_FILE = os.path.join(
    CREDENTIALS_PATH,
    'suite-scheduler-staging_client_secret_service_account.json')

# Service account secret json file used for prod project.
PROD_CLIENT_SECRETS_FILE = os.path.join(
    CREDENTIALS_PATH, 'suite-scheduler_client_secret_service_account.json')
