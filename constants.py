# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module containing the constants to be reused throughout suite_scheduler."""

import collections
import logging
import os

from google.appengine.api import app_identity

# Namedtuple for storing rest client info.
RestClientInfo = collections.namedtuple(
    'RestClientInfo', 'scopes, service_name, service_version')

# Constants for detecting the running environment.
_RUNNING_ENV = 'SERVER_SOFTWARE'
_ENV_DEVELOPMENT_STR = 'Development'
_ENV_APP_ENGINE_STR = 'Google App Engine/'


class StorageBucket(object):
  """Constants refer to Google storage bucket."""

  PROD_SUITE_SCHEDULER = 'suite-scheduler.google.com.a.appspot.com'


class AppID(object):
  """Constants refer to app id."""

  PROD_APP = 'suite-scheduler'
  STAGING_APP = 'suite-scheduler-staging'

class Metrics(object):
  """Constants for uplading analytic metrics."""

  PROJECT_ID_STAGING = 'google.com:suite-scheduler-staging'
  PROJECT_ID = 'google.com:suite-scheduler'
  DATASET = 'metrics'
  TRIGGER_EVENT_TABLE = 'trigger_events'
  EXECUTION_TASK_TABLE = 'execution_tasks'

class Buildbucket(object):
  """Constants used when making buildbucket calls."""

  HOST = 'cr-buildbucket.appspot.com'
  PROJECT = 'chromeos'
  BUCKET = 'testplatform'
  PROD_BUILDER = 'cros_test_platform'
  STAGING_BUILDER = 'cros_test_platform-dev'

  MAX_BUILDBUCKET_TIMEOUT_MINS = 46*60
  MAX_RETRY = 3

  # TODO(crbug.com/1034166): this is a workaround to reduce the child task count
  # in swarming.
  MULTIREQUEST_SIZE = 25


class BaseEvent(object):
  """Constants used for base_event."""

  # The new build may not get inserted to BQ right after they are
  # created(crbug/1038729). DELAY_HOURS delays the period of
  # the builds suite scheduler queries, to ensure the target
  # builds exist in BQ.
  DELAY_HOURS = 10


class CalendarID(object):
  """Constants refer to calendar id."""

  PROD_NEW_BUILD = (
      'google.com_8n9gndgp0o642d7ta7dakbiiso@group.calendar.google.com')
  PROD_NIGHTLY = (
      'google.com_e8p3i4pk80lt6snfb57fdgff3g@group.calendar.google.com')
  PROD_WEEKLY = (
      'google.com_9es5a7m1r9til9uf5qc8mpr6p4@group.calendar.google.com')
  STAGING_NEW_BUILD = (
      'google.com_pjlsd9371ic158vdgcacspu0m4@group.calendar.google.com')
  STAGING_NIGHTLY = (
      'google.com_lu3v13kr4if93l9embsvb5llj4@group.calendar.google.com')
  STAGING_WEEKLY = (
      'google.com_9l29i5ncfk24e5aktjr6gaerp8@group.calendar.google.com')


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

  STACKDRIVER_CLIENT = RestClientInfo._make(
      ['https://www.googleapis.com/auth/logging.read',
       'logging',
       'v2'])

  BIGQUERY_CLIENT = RestClientInfo._make(
      ['https://www.googleapis.com/auth/bigquery',
       'bigquery',
       'v2'])


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
  WEEKLY = 230

  # daily task's priority
  DAILY = 200

  # postbuild task's priority
  POSTBUILD = 170

  # the default task priority
  DEFAULT = 140


def environment():
  """Return proper environment settings."""
  if os.getenv(_RUNNING_ENV, '').startswith(_ENV_DEVELOPMENT_STR):
    return RunningEnv.ENV_DEVELOPMENT_SERVER
  elif os.getenv(_RUNNING_ENV, '').startswith(_ENV_APP_ENGINE_STR):
    return RunningEnv.ENV_PROD
  else:
    return RunningEnv.ENV_STANDALONE


def application_id(parse=True):
  """Get current running application id.

  Args:
    parse: whether to parse prefix of application id.

  Returns:
      If the id == 'None', return None;
      If it's a Google internal GAE whose id format is 'google.com:<name>' and
      parse is specified as True, return <name>;
      Otherwise, return the full id.
  """
  app_id = app_identity.get_application_id()
  logging.info('app_id: %s', app_id)
  if app_id == 'None':
    return None

  if not parse:
    return app_id

  if app_id is not None and len(app_id.split(':')) > 1:
    return app_id.split(':')[1]
  else:
    return app_id


def server_name():
  """Return server name.

  Returns:
    If this instance is running locally, return 'localhost:xxxx'.
    If this instance is running on GAE, return '***.googleplex.com' or
    '***.appspot.com'.
  """
  return app_identity.get_default_version_hostname()
