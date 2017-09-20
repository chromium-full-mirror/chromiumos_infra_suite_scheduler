# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for setup environemtn for local testing & Goole App Engine."""


import argparse
import os
import subprocess

import file_getter

import local_import  # pylint: disable=unused-import
try:
  from chromite.lib import gs  # pylint: disable=g-import-not-at-top
except ImportError:
  print 'Cannot import chromite'
  gs = None


# The credentials folder for suite-scheduler service.
CREDS_GS_PATH = 'gs://suite-scheduler.google.com.a.appspot.com/credentials/'


def _install_third_party_lib(input_args):
  """Install useful third-party lib.

  The libraries are specified in requirement.txt. They're used in both local
  development environment and Google App Engine, which means they will be
  uploaded to GAE.

  Args:
    input_args: the arguments passed in by users.
  """
  third_party_lib_path = file_getter.THIRD_PARTY_LIB_PATH
  if input_args.update_lib and os.path.exists(third_party_lib_path):
    os.rmdir(third_party_lib_path)

  if not os.path.exists(third_party_lib_path):
    print 'Creating lib path: %s' % third_party_lib_path
    os.mkdir(third_party_lib_path)
    print 'Installing packages'
    subprocess.check_call(
        ['pip', 'install', '-t', 'lib', '-r', 'requirements.txt'])


def _fetch_service_credentials(input_args):
  """Fetch service credentials from GS bucket.

  Args:
    input_args: the arguments passed in by users.

  Raises:
    ValueError: if credentials cannot be fetched due to no valid gs package.
  """
  credentials_path = file_getter.CREDENTIALS_PATH
  if input_args.update_cred and os.path.exists(credentials_path):
    os.rmdir(credentials_path)

  if not os.path.exists(credentials_path):
    if gs is None:
      raise ValueError(
          'Chromite cannot be imported. Please run gsutil directly to fetch '
          'credential files in %s' % input_args.creds_gs_path)

    os.mkdir(credentials_path)
    try:
      ctx = gs.GSContext(init_boto=True)
      ctx.Copy(input_args.creds_gs_path + '*', credentials_path)
    except gs.GSCommandError as e:
      print ('The GS credentials is not configured properly. '
             'Please contact ChromeOS Infrastructure'
             'team for more info about it.')
      print ('Failed to get suite_scheduler service credentials: %r.'
             'Deleting %s' % (str(e), credentials_path))
      os.rmdir(credentials_path)


def _verify():
  """Verify the credentials & third_party lib work."""
  subprocess.check_call(['python', 'runner.py'])


def _make_parser():
  """Return parser."""
  parser = argparse.ArgumentParser(
      description=__doc__,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--creds_gs_path',
      help='The path to fetch the credentials for project suite-scheduler.',
      default=CREDS_GS_PATH)
  parser.add_argument(
      '--update_lib',
      action='store_true',
      help='Force to reinstall all required third-party libraries.')
  parser.add_argument(
      '--update_cred',
      action='store_true',
      help='Force to re-copy the credentials from Google Storage.')
  return parser


if __name__ == '__main__':
  setup_parser = _make_parser()
  setup_args = setup_parser.parse_args()
  _install_third_party_lib(setup_args)
  _fetch_service_credentials(setup_args)
  _verify()
