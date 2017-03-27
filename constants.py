# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing the constants to be reused throughout suite_scheduler."""

from google.appengine.api import app_identity
from collections import namedtuple
import logging
import os

# Namedtuple for storing rest client info.
RestClientInfo = namedtuple(
    'RestClientInfo', 'scopes, service_name, service_version')


class RestClient(object):
    """Constants related to rest clients to google service."""

    # client info for connecting to android build API.
    ANDROID_BUILD_CLIENT = RestClientInfo._make(
        ['https://www.googleapis.com/auth/androidbuild.internal',
         'androidbuildinternal',
         'v2beta1'])

    # client info for connecting to google storage API.
    STORAGE_CLIENT = RestClientInfo._make(
        ['https://www.googleapis.com/auth/devstorage.full_control',
         'storage',
         'v1'])

    # client info for connecting to google calendar API.
    CALENDAR_CLIENT = RestClientInfo._make(
        ['https://www.googleapis.com/auth/calendar',
         'calendar',
         'v3'])

    SWARMING_CLIENT = RestClientInfo._make(
        ['https://www.googleapis.com/auth/userinfo.email',
         'swarming',
         'v1'])


class RunningEnv(object):
    """Constants related to app engine running environment."""

    # Running this GAE project locally with python.
    ENV_STANDALONE = 0

    # Running this GAE project with local development server.
    ENV_DEVELOPMENT_SERVER = 1

    # Running this GAE project in app-engine production.
    ENV_PROD = 2


class Priorities(object):
    """Constants related to task priority."""

    # weekly task's priority
    WEEKLY = 10

    # daily task's priority
    DAILY = 20

    # postbuild task's priority
    POSTBUILD = 30

    # the default task priority
    DEFAULT = 40


def environment():
    """Return proper environment settings."""
    if os.getenv(_RUNNING_ENV, '').startswith(_ENV_DEVELOPMENT_STR):
        return RunningEnv.ENV_DEVELOPMENT_SERVER
    elif os.getenv(_RUNNING_ENV, '').startswith(_ENV_APP_ENGINE_STR):
        return RunningEnv.ENV_PROD
    else:
        return RunningEnv.ENV_STANDALONE


def application_id():
    """Get current running application id.

    Returns:
        If it's a Google internal GAE whose id format is 'google.com:<name>',
        return <name>; Otherwise, return the full id.
    """
    app_id = app_identity.get_application_id()
    logging.info('app_id: %s', app_id)
    if app_id is not None and len(app_id.split(':')) > 1:
        return app_id.split(':')[1]
    else:
        return app_id


# Constants for detecting the running environment.
_RUNNING_ENV = 'SERVER_SOFTWARE'
_ENV_DEVELOPMENT_STR = 'Development'
_ENV_APP_ENGINE_STR = 'Google App Engine/'
