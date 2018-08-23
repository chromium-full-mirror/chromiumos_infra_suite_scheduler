# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for tests for handlers."""

import config_reader
import file_getter
import swarming_lib

import webapp2


class TestAFESwarmingAPI(webapp2.RequestHandler):

  def get(self):
    lab_config = config_reader.LabConfig(config_reader.ConfigReader(
        file_getter.LAB_CONFIG_FILE))
    afe_server = lab_config.get_dedicated_afe()
    swarming_runner = swarming_lib.SwarmingRunner(
        afe_server,
        swarming_lib.CHROME_STAGING_SWARMING_SERVER)
    afe_response = swarming_runner.dummy_run()
    afe_swarming_task_info = swarming_runner.query_task(afe_response['task_id'])
    self.response.write(afe_swarming_task_info.name)


class TestSkylabSwarmingAPI(webapp2.RequestHandler):

  def get(self):
    lab_config = config_reader.LabConfig(config_reader.ConfigReader(
        file_getter.LAB_CONFIG_FILE))
    afe_server = lab_config.get_dedicated_afe()
    swarming_runner = swarming_lib.SwarmingRunner(
        afe_server,
        swarming_lib.CHROME_STAGING_SWARMING_SERVER)
    skylab_response = swarming_runner.dummy_run(is_skylab=True)
    skylab_swarming_task_info = swarming_runner.query_task(
        skylab_response['task_id'], is_skylab=True)
    self.response.write(skylab_swarming_task_info.name)


class TestAFEWithSanity(webapp2.RequestHandler):

  def get(self):
    lab_config = config_reader.LabConfig(config_reader.ConfigReader(
        file_getter.LAB_CONFIG_FILE))
    afe_server = lab_config.get_dedicated_afe()
    swarming_runner = swarming_lib.SwarmingRunner(
        afe_server,
        swarming_lib.CHROME_STAGING_SWARMING_SERVER)
    skylab_response = swarming_runner.dummy_run_sanity(is_skylab=False)
    skylab_swarming_task_info = swarming_runner.query_task(
        skylab_response['task_id'], is_skylab=False)
    self.response.write(skylab_swarming_task_info.tags)


class TestSkylabWithSanity(webapp2.RequestHandler):

  def get(self):
    lab_config = config_reader.LabConfig(config_reader.ConfigReader(
        file_getter.LAB_CONFIG_FILE))
    afe_server = lab_config.get_dedicated_afe()
    swarming_runner = swarming_lib.SwarmingRunner(
        afe_server,
        swarming_lib.CHROME_STAGING_SWARMING_SERVER)
    skylab_response = swarming_runner.dummy_run_sanity(is_skylab=True)
    skylab_swarming_task_info = swarming_runner.query_task(
        skylab_response['task_id'], is_skylab=True)
    self.response.write(skylab_swarming_task_info.tags)


app = webapp2.WSGIApplication([
    ('/test_push/afe_dummy', TestAFESwarmingAPI),
    ('/test_push/skylab_dummy', TestSkylabSwarmingAPI),
    ('/test_push/afe_sanity', TestAFEWithSanity),
    ('/test_push/skylab_sanity', TestSkylabWithSanity),
    ], debug=True)
