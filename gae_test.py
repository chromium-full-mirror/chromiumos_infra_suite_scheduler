# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for tests for handlers."""

import datetime

import config_reader
import constants
import file_getter
import rest_client
import swarming_lib
import time_converter

import webapp2


class TestAFESwarmingAPI(webapp2.RequestHandler):

  def get(self):
    lab_config = config_reader.LabConfig(config_reader.ConfigReader(
        file_getter.LAB_CONFIG_FILE))
    afe_server = lab_config.get_dedicated_afe()
    swarming_runner = swarming_lib.SwarmingRunner(
        afe_server,
        swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
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
        swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
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
        swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
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
        swarming_lib.SKYLAB_SWARMING_SERVER)
    skylab_response = swarming_runner.dummy_run_sanity(is_skylab=True)
    skylab_swarming_task_info = swarming_runner.query_task(
        skylab_response['task_id'], is_skylab=True)
    self.response.write(skylab_swarming_task_info.tags)


class TestSkylabBackwardCompatibilityWithSanity(webapp2.RequestHandler):

  def get(self):
    lab_config = config_reader.LabConfig(config_reader.ConfigReader(
        file_getter.LAB_CONFIG_FILE))
    afe_server = lab_config.get_dedicated_afe()
    swarming_runner = swarming_lib.SwarmingRunner(
        afe_server,
        swarming_lib.SKYLAB_SWARMING_SERVER)
    skylab_response = swarming_runner.dummy_run_sanity_old(is_skylab=True)
    skylab_swarming_task_info = swarming_runner.query_task(
        skylab_response['task_id'], is_skylab=True)
    self.response.write(skylab_swarming_task_info.tags)


class _FakeBigqueryGetPassedHandler(webapp2.RequestHandler):

  def get(self):
    bq_client = rest_client.BuildBucketBigqueryClient(
        rest_client.BaseRestClient(
            constants.RestClient.BIGQUERY_CLIENT.scopes,
            constants.RestClient.BIGQUERY_CLIENT.service_name,
            constants.RestClient.BIGQUERY_CLIENT.service_version))

    # Get passed builds in 3 days.
    utc_now = time_converter.utc_now()
    since_date = utc_now - datetime.timedelta(days=3)
    res = bq_client.get_passed_builds_since_date(since_date)
    for r in res:
      self.response.write(r)
      self.response.write('\n')


class _FakeBigqueryGetRelaxedPassedHandler(webapp2.RequestHandler):

  def get(self):
    bq_client = rest_client.BuildBucketBigqueryClient(
        rest_client.BaseRestClient(
            constants.RestClient.BIGQUERY_CLIENT.scopes,
            constants.RestClient.BIGQUERY_CLIENT.service_name,
            constants.RestClient.BIGQUERY_CLIENT.service_version))

    # Get passed builds in 3 days.
    utc_now = time_converter.utc_now()
    since_date = utc_now - datetime.timedelta(days=3)
    res = bq_client.get_relaxed_passed_builds_since_date(since_date)
    for r in res:
      self.response.write(r)
      self.response.write('\n')


app = webapp2.WSGIApplication([
    ('/test_push/afe_dummy', TestAFESwarmingAPI),
    ('/test_push/skylab_dummy', TestSkylabSwarmingAPI),
    ('/test_push/afe_sanity', TestAFEWithSanity),
    ('/test_push/skylab_sanity', TestSkylabWithSanity),
    ('/test_push/skylab_sanity_bc_test',
     TestSkylabBackwardCompatibilityWithSanity),
    ('/test_push/bq_get_passed', _FakeBigqueryGetPassedHandler),
    ('/test_push/bq_get_relaxed_passed', _FakeBigqueryGetRelaxedPassedHandler),
    ], debug=True)
