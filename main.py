# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for cron jobs kicked off by suite scheduler."""
# pylint: disable=g-bad-import-order

import jinja2
import os
import webapp2

import constants
import rest_client
import stackdriver_lib


# jinja environment for embedding website.
_JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class MainDashboard(webapp2.RequestHandler):
  """Main page for suite scheduler."""

  def get(self):
    template_values = {'app_id': constants.application_id()}
    template = _JINJA_ENVIRONMENT.get_template('www/index.html')
    self.response.write(template.render(template_values))


class TriggerLog(webapp2.RequestHandler):
  """Log page for suite scheduler cron job: trigger_event."""

  def get(self):
    self.response.headers['Content-Type'] = 'text/plain'
    start_time = self.request.get('start_time')
    end_time = self.request.get('end_time')
    app_id = self.request.get('app_id')
    resource = self.request.get('resource')
    if not app_id:
      app_id = constants.application_id(parse=False)

    # In local development server
    if app_id is None:
      self.response.write('Local development server is probably running, '
                          'please specify app_id.')

    if not (start_time and end_time and resource):
      self.response.write('Invalid input parameters \nstart_time: %s\n'
                          'end_time: %s\nresource: %s\n' % (
                              start_time, end_time, resource))

    stackdriver_logging_client = rest_client.StackdriverRestClient(
        rest_client.BaseRestClient(
            constants.RestClient.STACKDRIVER_CLIENT.scopes,
            constants.RestClient.STACKDRIVER_CLIENT.service_name,
            constants.RestClient.STACKDRIVER_CLIENT.service_version))
    request = stackdriver_lib.form_logging_client_request(
        app_id,
        start_time,
        end_time,
        resource)
    logs = stackdriver_logging_client.read_logs(request)
    self.response.write(stackdriver_lib.parse_logging_client_response(logs))


app = webapp2.WSGIApplication([
    ('/', MainDashboard),
    ('/trigger_event_log', TriggerLog),
], debug=True)
