# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for unittest framework.

This program handles properly importing the App Engine SDK so that test modules
can use google.appengine.* APIs and the Google App Engine testbed.

Example invocation:
    $ python runner.py ~/google-cloud-sdk [your sdk path]
"""

import argparse
import logging
import os
import sys
import unittest

# Set GOOGLE_CLOUD_SDK_PATH in user's home directory ~/.
GOOGLE_CLOUD_SDK_PATH = os.path.join(
    os.path.expanduser('~'), 'google-cloud-sdk')

# Mapping between test type and test files' pattern.
TEST_PATTERN_MAP = {'unittest': '*_unittest.py',
                    'integration': '*_integration_test.py'}


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


def main(input_args):
  """The main function to run unittest/integration tests.

  Args:
    input_args: the input args.

  Returns:
    a unittest.TextTestRunner object.
  """
  if input_args.sdk_path != GOOGLE_CLOUD_SDK_PATH:
    _import_sdk_path(input_args.sdk_path)

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

  # Discover and run tests.
  if input_args.test_file:
    suites = unittest.loader.TestLoader().discover(
        input_args.test_path, input_args.test_file)
  else:
    suites = unittest.loader.TestLoader().discover(
        input_args.test_path, TEST_PATTERN_MAP[input_args.test_type])

  return unittest.TextTestRunner(verbosity=2).run(suites)


def _import_sdk_path(sdk_path):
  # If the SDK path points to a Google Cloud SDK installation
  # then we should alter it to point to the GAE platform location.
  appengine_path = os.path.join(sdk_path, 'platform/google_appengine')
  sdk_path = appengine_path if os.path.exists(appengine_path) else sdk_path

  # Make sure google.appengine.* modules are importable.
  fixup_paths(sdk_path)

  # Make sure all bundled third-party packages are available.
  # pylint: disable=g-import-not-at-top
  import dev_appserver
  dev_appserver.fix_sys_path()


def _make_parser():
  """Return unittest parser."""
  parser = argparse.ArgumentParser(
      description=__doc__,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--sdk_path',
      help='The path to the Google App Engine SDK or the Google Cloud SDK.',
      default=GOOGLE_CLOUD_SDK_PATH)
  parser.add_argument(
      '--test_path',
      help='The path to look for tests, defaults to the current directory.',
      default=os.getcwd())
  group = parser.add_mutually_exclusive_group()
  group.add_argument(
      '--test_type', choices=['unittest', 'integration'],
      help=('The test type, including unittest and integration test, defaults '
            'to unittest'),
      default='unittest')
  group.add_argument(
      'test_file',
      nargs='?',
      help=('A single test module to test, default to empty string, which '
            'means the runner will find test modules by test-pattern.'),
      default='')
  parser.add_argument(
      '--debug',
      action='store_true',
      help='Display the logging in unittest.')
  return parser


if __name__ == '__main__':
  unittest_parser = _make_parser()
  args = unittest_parser.parse_args()
  if args.debug:
    logging.getLogger().setLevel(logging.DEBUG)
  else:
    logging.getLogger().setLevel(logging.CRITICAL)

  try:
    _import_sdk_path(args.sdk_path)
  except ImportError:
    args.sdk_path = raw_input('Cannot find google SDK in %s. Please specify '
                              'your google SDK path: ' % GOOGLE_CLOUD_SDK_PATH)

  result = main(args)

  if not result.wasSuccessful():
    sys.exit(1)
