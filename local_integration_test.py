# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for local integration tests."""

import datetime
import logging
import os
import subprocess
import unittest

import constants
import stackdriver_lib
import swarming_lib
import time_converter
import utils


# The local dev_appserver script, only available when Google App Engine SDK
# is set.
LOCAL_DEV_APPSERVER = 'dev_appserver.py'

# The configuration file for local integration test.
INTEGRATION_TEST_CONFIG = 'test.yaml'

# Indicate whether it's in debug.
DEBUG_MODE = logging.getLogger().getEffectiveLevel() <= logging.DEBUG

# The url to start local dev appserver.
DEV_APPSERVER_PORT = 8888
DEV_APPSERVER_URL = 'http://localhost:%d' % DEV_APPSERVER_PORT
DEV_APPSERVER_ADMIN_PORT = 8001


def _subprocess_wrapper(func, cmd, **kwargs):
  if DEBUG_MODE:
    return func(cmd, **kwargs)
  else:
    with open(os.devnull, 'w') as devnull:
      return func(cmd, stderr=devnull, **kwargs)


def _check_dev_appserver():
  """Wait for dev_appserver to start for integration tests.

  Returns:
    The output of calling DEV_APPSERVER_URL/check_health.

  Raises:
    subprocess.CalledProcessError: if the url is not working.
  """
  return _subprocess_wrapper(
      subprocess.check_output,
      ['curl', '%s/check_health' % DEV_APPSERVER_URL])


class IntegrationTest(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    # In order to only start dev_appserver once for all tests, use setUpClass
    # here. However there's no corresponding addCleanUp() for this class
    # function, so use 'try except' to terminate the dev_appserver process.
    try:
      cls.dev_app_proc = _subprocess_wrapper(
          subprocess.Popen,
          ['%s %s --port %d --admin_port %d --log_level=debug' %
           (LOCAL_DEV_APPSERVER, INTEGRATION_TEST_CONFIG,
            DEV_APPSERVER_PORT, DEV_APPSERVER_ADMIN_PORT)],
          shell=True)

      # Wait for dev_appserver to start locally.
      utils.wait_for_value(
          _check_dev_appserver,
          exception_to_raise=subprocess.CalledProcessError)
    except:
      cls.tearDownClass()
      # Still raise error to indicate that tests fail.
      raise

  @classmethod
  def tearDownClass(cls):
    cls.dev_app_proc.terminate()

  def testSwarmingDummyRun(self):
    """Swarming test with local configs and dev_appservers."""
    output = _subprocess_wrapper(
        subprocess.check_output,
        ['curl', '%s/test_push/swarming' % DEV_APPSERVER_URL])
    self.assertEqual(output, swarming_lib.DUMMY_TASK_NAME)

  def testTriggerEventLogs(self):
    """RPC test for trigger_event_log."""
    current_time = time_converter.utc_now()
    start_time = current_time - datetime.timedelta(hours=12)
    log_format = ('%s/trigger_event_log?start_time=%s&end_time=%s&'
                  'resource=%s&app_id=%s')
    log_url = log_format % (
        DEV_APPSERVER_URL,
        start_time.strftime(time_converter.STACKDRIVER_TIME_FORMAT),
        current_time.strftime(time_converter.STACKDRIVER_TIME_FORMAT),
        '/cron/test_push',
        'google.com:%s' % constants.AppID.STAGING_APP)
    output = _subprocess_wrapper(subprocess.check_output, ['curl', log_url])
    self.assertEqual(len(output.splitlines()[0].split('|')),
                     len(stackdriver_lib.LOGGING_FORMAT.split('|')))


if __name__ == '__main__':
  unittest.main()
