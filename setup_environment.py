# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Module for setup environemtn for local testing & Google App Engine."""

from __future__ import print_function

import argparse
import collections
import os
import shutil
import subprocess

import file_getter

import local_import  # pylint: disable=unused-import
try:
  from chromite.lib import gs  # pylint: disable=g-import-not-at-top
except ImportError:
  print('Cannot import chromite')
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
    print('Creating lib path: %s' % third_party_lib_path)
    os.mkdir(third_party_lib_path)
    print('Installing packages')
    cmd = ['pip', 'install', '-t', 'lib', '-r', 'requirements.txt']
    try:
      subprocess.check_call(cmd)
    except subprocess.CalledProcessError:
      # TODO(crbug.com/792690): this is a workround of fixing installing
      # third-party packages on different versions of Ubuntu/Debian.
      print("Failed to run '%s'; trying a different command." % ' '.join(cmd))
      subprocess.check_call([
          'pip', 'install', '-t', 'lib', '--system', '-r', 'requirements.txt'
      ])


# _GitDep specifies a dependency in the form of a particular reference in a git
# project.
_GitDep = collections.namedtuple('_GitDep', 'local_name git_project git_ref')

# List of all git project dependencies.
_GIT_DEPS = [
    _GitDep(
        'chromite',
        'https://chromium.googlesource.com/chromiumos/chromite',
        'bf296fb827fe998bc174ad7e456534d4c7847ea5',
    ),
    _GitDep(
        'luci',
        'https://chromium.googlesource.com/infra/luci/luci-py',
        '33a910c714948a5189f9c58101ce9b131f01c1fd',
    ),
]


def _install_infra_libs():
  """Install useful libs from Chromium infra and Chromite.

  infra_libs consists of prpc client from luci and necessary proto files from
  Chromite. Suite scheduler relies on those libs to conduct prpc call to
  Buildbucket.
  """
  infra_libs_path = file_getter.INFRA_LIBS_PATH
  print('Recreate infra_libs directory if already exists...')
  if os.path.exists(infra_libs_path):
    shutil.rmtree(infra_libs_path)
  os.mkdir(infra_libs_path)

  for dep in _GIT_DEPS:
    dep_path = os.path.join(infra_libs_path, dep.local_name)
    print('Cloning %s at %s in %s' % (dep.git_project, dep.git_ref, dep_path))
    subprocess.check_call(['git', 'clone', dep.git_project, dep.local_name],
                          cwd=infra_libs_path)
    subprocess.check_call(['git', 'checkout', dep.git_ref], cwd=dep_path)


def _fetch_service_credentials():
  """Fetch service credentials from GS bucket.

  Raises:
    ValueError: if credentials cannot be fetched due to no valid gs package.
  """
  credentials_path = file_getter.CREDENTIALS_PATH
  if os.path.exists(credentials_path):
    print('The credential folder already exists: %s. '
          'Delete it if you want to reload the service accounts.' %
          credentials_path)
    return

  if gs is None:
    raise ValueError(
        'Chromite cannot be imported.\nPlease download the credentials '
        'manually:\n\tgsutil cp -r %s %s' %
        (CREDS_GS_PATH, os.path.dirname(credentials_path)))

  os.mkdir(credentials_path)
  try:
    ctx = gs.GSContext(init_boto=True)
    ctx.Copy(CREDS_GS_PATH + '*', credentials_path)
  except gs.GSCommandError as e:
    print('The GS credentials is not configured properly. '
          'Please contact ChromeOS Infrastructure'
          'team for more info about it.')
    print('Failed to get suite_scheduler service credentials: %r.'
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
      '--update_lib',
      action='store_true',
      help='Force to reinstall all required third-party libraries.')
  parser.add_argument('--load_cred',
                      action='store_true',
                      help='Load credentials from Google Storage.')
  parser.add_argument('--load_infra_libs',
                      action='store_true',
                      help='Install infra libs.')
  parser.add_argument('--run_unit_test',
                      action='store_true',
                      help='Run unit test.')
  return parser


if __name__ == '__main__':
  setup_parser = _make_parser()
  setup_args = setup_parser.parse_args()
  _install_third_party_lib(setup_args)
  if setup_args.load_cred:
    _fetch_service_credentials()
  if setup_args.load_infra_libs:
    _install_infra_libs()
  if setup_args.run_unit_test:
    _verify()
