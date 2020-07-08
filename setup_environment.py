# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Module for setup environemtn for local testing & Google App Engine.

DO NOT RUN THIS MODULE DIRECTLY.

Use bin/setup_environment instead.
See [README.md].
"""

from __future__ import print_function

import argparse
import collections
import os
import pipes
import shutil
import subprocess
import sys

_ROOT = os.path.dirname(os.path.realpath(__file__))

_INFRA_LIBS_PATH = os.path.join(_ROOT, 'infra_libs')
_REFRESH_CREDENTIALS_SCRIPT = os.path.join(_ROOT, 'bin', 'refresh_credentials')
_REQUIREMENTS_PATH = os.path.join(_ROOT, "requirements.txt")
_THIRD_PARTY_LIB_PATH = os.path.join(_ROOT, 'lib')


def _install_third_party_lib():
  """Install useful third-party lib.

  The libraries are specified in requirement.txt. They're used in both local
  development environment and Google App Engine, which means they will be
  uploaded to GAE.
  """
  if os.path.exists(_THIRD_PARTY_LIB_PATH):
    shutil.rmtree(_THIRD_PARTY_LIB_PATH)
  os.mkdir(_THIRD_PARTY_LIB_PATH)
  print('Installing third party dependencies in %s' %
        (_THIRD_PARTY_LIB_PATH, ))
  try:
    subprocess.check_call([
        sys.executable, '-m', 'pip', 'install', '-t', _THIRD_PARTY_LIB_PATH,
        '-r', _REQUIREMENTS_PATH
    ])
  except OSError:
    print('Please check that `pip` is installed. See README.md')
    raise


# _GitDep specifies a dependency in the form of a particular reference in a git
# project.
#
#   local_name: Name of the local directory to fetch into.
#   project: URL to the git project to fetch from.
#   ref: Git ref to fetch.
#   sparse_checkout_paths: A list of paths to checkout. Some of the dependencies
#     contain too many files and AppEngine does not allow uploading > 10K files.
#     Thus, we checkout only required sub-packages. This list is passed in to
#     (and interpreted by) `git sparse-checkout`.
_GitDep = collections.namedtuple(
    '_GitDep', 'local_name git_project git_ref sparse_checkout_paths')

# List of all git project dependencies.
_GIT_DEPS = [
    _GitDep(
        'chromite',
        'https://chromium.googlesource.com/chromiumos/chromite',
        'bf296fb827fe998bc174ad7e456534d4c7847ea5',
        [
            '/api/gen/**/*.py', '/api/__init__.py',
            '/third_party/infra_libs/*', '/third_party/google/*',
            '/third_party/__init__.py', '/__init__.py', '!*test.py'
        ],
    ),
    _GitDep(
        'luci',
        'https://chromium.googlesource.com/infra/luci/luci-py',
        '33a910c714948a5189f9c58101ce9b131f01c1fd',
        [
            '/appengine/components/components/auth/**/*.py',
            '/appengine/components/components/datastore_utils/**/*.py',
            '/appengine/components/components/prpc/**/*.py',
            '/appengine/components/components/*.py', '!*test.py'
        ],
    ),
]


def _install_infra_libs():
  """Install useful libs from Chromium infra and Chromite.

  infra_libs consists of prpc client from luci and necessary proto files from
  Chromite. Suite scheduler relies on those libs to conduct prpc call to
  Buildbucket.
  """
  if os.path.exists(_INFRA_LIBS_PATH):
    shutil.rmtree(_INFRA_LIBS_PATH)
  os.mkdir(_INFRA_LIBS_PATH)

  for dep in _GIT_DEPS:
    dep_path = os.path.join(_INFRA_LIBS_PATH, dep.local_name)
    print('Creating sparse checkout of %s at %s in %s' %
          (dep.git_project, dep.git_ref, dep_path))
    subprocess.check_call(
        ['git', 'clone', '--no-checkout', dep.git_project, dep.local_name],
        cwd=_INFRA_LIBS_PATH)
    subprocess.check_call(['git', 'sparse-checkout', 'init'], cwd=dep_path)
    _set_sparse_checkout_paths(dep_path, dep.sparse_checkout_paths)
    subprocess.check_call(
        ['git', 'checkout', dep.git_ref, '-b', 'deploy', '-f'], cwd=dep_path)


def _set_sparse_checkout_paths(checkout_dir, sparse_checkout_paths):
  """Set the path patterns to checkout in a git checkout."""
  # Pass in path patterns via stdin to avoid shell escaping issues.
  proc = subprocess.Popen(['git', 'sparse-checkout', 'set', '--stdin'],
                          stdin=subprocess.PIPE,
                          cwd=checkout_dir)
  proc.communicate(input='\n'.join(sparse_checkout_paths))
  if proc.poll() is None:
    raise Exception('Leaked process when setting sparse checkout paths')
  if proc.poll() != 0:
    raise Exception('Failed to set sparse checkout paths')


def _load_credentials():
  subprocess.check_call([_REFRESH_CREDENTIALS_SCRIPT])


def main():
  """Entry point of the script"""
  parser = argparse.ArgumentParser(
      description=__doc__,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--load-creds',
      action='store_true',
      help='Also install credentials needed for releasing suite '
      'scheduler. Not needed to modify config/*')

  args = parser.parse_args()
  _install_third_party_lib()
  _install_infra_libs()
  if args.load_creds:
    _load_credentials()


if __name__ == '__main__':
  main()
