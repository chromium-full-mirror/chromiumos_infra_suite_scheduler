# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for import required libraries/configs."""

import os
import sys


# Set GOOGLE_CLOUD_SDK_PATH in user's home directory ~/.
GOOGLE_CLOUD_SDK_PATH = '/usr/lib/google-cloud-sdk'


def import_appengine_config():
  """Import AppEngine config."""
  # Loading appengine_config from the current project ensures that any
  # changes to configuration there are available to all tests (e.g.
  # sys.path modifications, namespaces, etc.)
  try:
    # pylint: disable=g-import-not-at-top
    import appengine_config
    # pylint: disable=pointless-statement
    (appengine_config)
  except ImportError:
    print 'Note: unable to import appengine_config.'


def import_sdk_path(sdk_path=GOOGLE_CLOUD_SDK_PATH):
  """Import the Google App Engine SDK based on given sdk_path.

  Args:
    sdk_path: The Google App Engine SDK path. By default it's
      GOOGLE_CLOUD_SDK_PATH.
  """
  # If the SDK path points to a Google Cloud SDK installation, then we
  # should alter it to point to the GAE platform location.
  appengine_path = os.path.join(sdk_path, 'platform/google_appengine')
  sdk_path = appengine_path if os.path.exists(appengine_path) else sdk_path

  # Make sure google.appengine.* modules are importable.
  fixup_paths(sdk_path)

  # Make sure all bundled third-party packages are available.
  # pylint: disable=g-import-not-at-top
  import dev_appserver
  dev_appserver.fix_sys_path()


def fixup_paths(path):
  """Adds GAE SDK path to system path and appends it to the google path.

  Not all Google packages are inside namespace packages, which means
  there might be another non-namespace package named `google` already on
  the path and simply appending the App Engine SDK to the path will not
  work since the other package will get discovered and used first.
  This emulates namespace packages by first searching if a `google` package
  exists by importing it, and if so appending to its module search path.

  Args:
    path: the path of GAE SDK.
  """
  try:
    # pylint: disable=g-import-not-at-top
    import google
    google.__path__.append('{0}/google'.format(path))
  except ImportError:
    pass

  sys.path.insert(0, path)
