# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for tests for handlers."""

import swarming_lib

import webapp2


class TestSwarmingAPI(webapp2.RequestHandler):

  def get(self):
    swarming_runner = swarming_lib.SwarmingRunner()
    response = swarming_runner.dummy_run()
    swarming_task_info = swarming_runner.query_task(response['task_id'])
    self.response.write(swarming_task_info.name)


app = webapp2.WSGIApplication([
    ('/test_push/swarming', TestSwarmingAPI),
    ], debug=True)
