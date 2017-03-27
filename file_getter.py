# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for fetching files used by suite scheduler."""

import os

import constants

# The path to save credentials.
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), 'credentials')

# Credentials for Cloud SQL connection
SQL_CREDENTIAL_FILE = os.path.join(CREDENTIALS_PATH,
                                   'cloud_sql_credentials.txt')

# The path to save configs.
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'configs')

# Suite scheduler event config file
SUITE_SCHEDULER_CONFIG_FILE = os.path.join(CONFIG_PATH, 'suite_scheduler.ini')

# Lab config file
LAB_CONFIG_FILE = os.path.join(CONFIG_PATH, 'lab_config.ini')

# Service account secret json file used for local development.
LOCAL_CLIENT_SECRETS_FILE = os.path.join(
    CREDENTIALS_PATH, 'suite-scheduler_client_secret_service_account.json')
