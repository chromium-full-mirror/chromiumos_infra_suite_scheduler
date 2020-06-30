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

import gae_import


# Mapping between test type and test files' pattern.
TEST_PATTERN_MAP = {'unittest': '*_unittest.py',
                    'integration': '*_integration_test.py',
                    'sanity': '*sanity_test.py'}


def main(input_args):
  """The main function to run unittest/integration tests.

  Args:
    input_args: the input args.

  Returns:
    a unittest.TextTestRunner object.
  """
  if input_args.sdk_path != gae_import.GOOGLE_CLOUD_SDK_PATH:
    gae_import.import_sdk_path(input_args.sdk_path)

  gae_import.import_appengine_config()

  # Discover and run tests.
  if input_args.test_file:
    suites = unittest.loader.TestLoader().discover(
        input_args.test_path, input_args.test_file)
  else:
    suites = unittest.loader.TestLoader().discover(
        input_args.test_path, TEST_PATTERN_MAP[input_args.test_type])

  return unittest.TextTestRunner(verbosity=2).run(suites)


def _make_parser():
  """Return unittest parser."""
  parser = argparse.ArgumentParser(
      description=__doc__,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--sdk_path',
      help='The path of Google App Engine SDK and Google Cloud SDK.',
      default=gae_import.GOOGLE_CLOUD_SDK_PATH)
  parser.add_argument(
      '--test_path',
      help='The path to look for tests, defaults to the current directory.',
      default=os.getcwd())
  group = parser.add_mutually_exclusive_group()
  group.add_argument(
      '--test_type', choices=['unittest', 'integration', 'sanity'],
      help=('The test type, including unittest, integration tests and sanity '
            'tests, defaults to unittest'),
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

  # Normalize to full path in case user input path is in abbreviated form.
  args.sdk_path = os.path.abspath(os.path.expanduser(args.sdk_path))

  try:
    gae_import.import_sdk_path(args.sdk_path)
  except ImportError:
    print('Cannot find google SDK in %s. Please specify a correct Google '
          'Cloud SDK path through --sdk_path flag.' % args.sdk_path)
    sys.exit(1)

  result = main(args)

  if not result.wasSuccessful():
    sys.exit(1)
