# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for tests for handlers."""

import datetime

import buildbucket
import constants
import rest_client
import time_converter

import webapp2


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
    res = bq_client.get_passed_builds(since_date, utc_now)
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
    res = bq_client.get_relaxed_passed_builds(since_date, utc_now)
    for r in res:
      self.response.write(r)
      self.response.write('\n')


class _FakeCrOSTestPlatformBigqueryHandler(webapp2.RequestHandler):

  def get(self):
    bq_client = rest_client.CrOSTestPlatformBigqueryClient(
        rest_client.BaseRestClient(
            constants.RestClient.BIGQUERY_CLIENT.scopes,
            constants.RestClient.BIGQUERY_CLIENT.service_name,
            constants.RestClient.BIGQUERY_CLIENT.service_version))
    res = bq_client.get_past_job_nums(72)
    if res > 0:
      self.response.write('ok')


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
    ('/test_push/bq_get_passed', _FakeBigqueryGetPassedHandler),
    ('/test_push/bq_get_relaxed_passed', _FakeBigqueryGetRelaxedPassedHandler),
    ('/test_push/bq_get_last_hours', _FakeCrOSTestPlatformBigqueryHandler),
    ('/test_push/buildbucket_lib_compatibility',
     _FakeBuildbucketLibCompatibilityHandler)
    ], debug=True)
