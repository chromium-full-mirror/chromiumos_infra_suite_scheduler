# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for local integration tests."""

import logging
import os
import subprocess
import unittest

import swarming_lib
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
    super(IntegrationTest, cls).setUpClass()
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
    super(IntegrationTest, cls).tearDownClass()
    cls.dev_app_proc.terminate()

  def testAFESwarmingDummyRun(self):
    """Swarming test with local configs and dev_appservers."""
    output = _subprocess_wrapper(
        subprocess.check_output,
        ['curl', '%s/test_push/afe_dummy' % DEV_APPSERVER_URL])
    self.assertEqual(output, swarming_lib.DUMMY_TASK_NAME)

  def testSkylabSwarmingDummyRun(self):
    """Swarming test with local configs and dev_appservers."""
    output = _subprocess_wrapper(
        subprocess.check_output,
        ['curl', '%s/test_push/skylab_dummy' % DEV_APPSERVER_URL])
    self.assertEqual(output, swarming_lib.DUMMY_TASK_NAME)

  def testAFESwarmingSanity(self):
    """Swarming test with local configs and dev_appservers."""
    output = _subprocess_wrapper(
        subprocess.check_output,
        ['curl', '%s/test_push/afe_sanity' % DEV_APPSERVER_URL])
    self.assertIn('sanity', output)

  def testSkylabSwarmingSanity(self):
    """Swarming test with local configs and dev_appservers."""
    output = _subprocess_wrapper(
        subprocess.check_output,
        ['curl', '%s/test_push/skylab_sanity' % DEV_APPSERVER_URL])
    self.assertIn('sanity', output)

  def testSkylabBackwardCompatibilitySwarmingSanity(self):
    """Swarming test with local configs and dev_appservers."""
    output = _subprocess_wrapper(
        subprocess.check_output,
        ['curl', '%s/test_push/skylab_sanity_bc_test' % DEV_APPSERVER_URL])
    self.assertIn('sanity', output)

  def testBigqueryGetPassedFromBB(self):
    """Test get_passed_builds from Buildbucket Bigquery database."""
    output = _subprocess_wrapper(
        subprocess.check_output,
        ['curl', '%s/test_push/bq_get_passed' % DEV_APPSERVER_URL])
    self.assertIn('release', output)

  def testBigqueryGetRelaxedPassedFromBB(self):
    """Test get_relaxed_passed_builds from Buildbucket Bigquery database."""
    output = _subprocess_wrapper(
        subprocess.check_output,
        ['curl', '%s/test_push/bq_get_relaxed_passed' % DEV_APPSERVER_URL])
    self.assertIn('release', output)

  def testBigqueryGetJobsLastHours(self):
    """Test get_past_buildbucket_job_nums from cros_test_platform BQ database"""
    output = _subprocess_wrapper(
        subprocess.check_output,
        ['curl', '%s/test_push/bq_get_last_hours' % DEV_APPSERVER_URL])
    self.assertIn('ok', output)

  def testBuildbucketClient(self):
    """Test buildbucket client by calling test-platform's dev builder."""
    output = _subprocess_wrapper(
        subprocess.check_output,
        ['curl', '%s/test_push/buildbucket_lib_compatibility'
         % DEV_APPSERVER_URL])
    self.assertIn('status: SCHEDULED', output)


if __name__ == '__main__':
  unittest.main()
