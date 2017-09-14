# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for cron jobs kicked off by suite scheduler."""
# pylint: disable=g-bad-import-order

import jinja2
import os
import webapp2

import constants


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


app = webapp2.WSGIApplication([
    ('/', MainDashboard),
], debug=True)


