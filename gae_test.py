# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for tests for handlers."""

import datetime

import buildbucket
import config_reader
import constants
import file_getter
import rest_client
import swarming_lib
import time_converter

import webapp2


class _FakeAFESwarmingAPIHandler(webapp2.RequestHandler):

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


class _FakeSkylabSwarmingAPIHandler(webapp2.RequestHandler):

  def get(self):
    lab_config = config_reader.LabConfig(config_reader.ConfigReader(
        file_getter.LAB_CONFIG_FILE))
    afe_server = lab_config.get_dedicated_afe()
    swarming_runner = swarming_lib.SwarmingRunner(
        afe_server,
        swarming_lib.SKYLAB_STAGING_SWARMING_SERVER)
    skylab_response = swarming_runner.dummy_run(is_skylab='True')
    skylab_swarming_task_info = swarming_runner.query_task(
        skylab_response['task_id'], is_skylab=True)
    self.response.write(skylab_swarming_task_info.name)


class _FakeAFEWithSanityHandler(webapp2.RequestHandler):

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


class _FakeSkylabWithSanityHandler(webapp2.RequestHandler):

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


class _FakeSkylabBackwardCompatibilityWithSanityHandler(webapp2.RequestHandler):

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


class _FakeBuildbucketLibCompatibilityHandler(webapp2.RequestHandler):

  def get(self):
    test_platform_client = buildbucket.TestPlatformClient(
        constants.Buildbucket.HOST,
        constants.Buildbucket.PROJECT,
        constants.Buildbucket.BUCKET,
        constants.Buildbucket.STAGING_BUILDER)
    res = test_platform_client.dummy_run()
    self.response.write(res)


app = webapp2.WSGIApplication([
    ('/test_push/afe_dummy', _FakeAFESwarmingAPIHandler),
    ('/test_push/skylab_dummy', _FakeSkylabSwarmingAPIHandler),
    ('/test_push/afe_sanity', _FakeAFEWithSanityHandler),
    ('/test_push/skylab_sanity', _FakeSkylabWithSanityHandler),
    ('/test_push/skylab_sanity_bc_test',
     _FakeSkylabBackwardCompatibilityWithSanityHandler),
    ('/test_push/bq_get_passed', _FakeBigqueryGetPassedHandler),
    ('/test_push/bq_get_relaxed_passed', _FakeBigqueryGetRelaxedPassedHandler),
    ('/test_push/buildbucket_lib_compatibility',
     _FakeBuildbucketLibCompatibilityHandler)
    ], debug=True)
