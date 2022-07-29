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


def create_file(fname):
  """Create an empty file by opening it for writing and closing."""
  open(fname, 'w').close()


def fixup_chromite_imports():
  """Fixup chromite __init__.py files.

  Chromite runs Python3 now so relies on implicit namespacing, which Python2
  doesn't support, so we have to go back and add a few __init__.py files to make
  things importable.
  """
  def remove_third_party(fname, package):
    "Remove 'chromite.third_party.' prefix from given import string."
    cmd = [
        'sed',
        '-i',
        's/%s/%s/' % ('chromite.third_party.%s' % package, package),
        fname,
    ]
    subprocess.check_call(cmd)

  for root, _, files in os.walk('infra_libs/chromite'):
    for fname in files:
      if fname.endswith('_pb2.py'):
        path = os.path.join(root, fname)
        remove_third_party(path, 'google.protobuf')

  # Add explicit __init__.py files to workaround implicit namespaces in python3
  create_file('infra_libs/chromite/__init__.py')
  create_file('infra_libs/chromite/third_party/__init__.py')
  create_file('infra_libs/chromite/third_party/google/__init__.py')
  create_file('infra_libs/chromite/third_party/google/api/__init__.py')


# _GITDEP Specifies a dependency in the form of a particular reference in a git
# project.
#
#   local_name: Name of the local directory to fetch into.
#   project: URL to the git project to fetch from.
#   ref: Git ref to fetch.
#   sparse_checkout_paths: A list of paths to checkout. Some of the dependencies
#     contain too many files and AppEngine does not allow uploading > 10K files.
#     Thus, we checkout only required sub-packages. This list is passed in to
#     (and interpreted by) `git sparse-checkout`.
#   post_process: An optional callable to evaluate after cloning dependency
_GitDep = collections.namedtuple(
    '_GitDep',
    'local_name git_project git_ref sparse_checkout_paths post_process')

# List of all git project dependencies.
_GIT_DEPS = [
    # Note:  When upreving chromite, ensure that protobuf version in
    # requirements.txt still matches the protobuf version used by chromite.
    _GitDep(
        'chromite',
        'https://chromium.googlesource.com/chromiumos/chromite',
        '1678d4792a11268172ff7ff79535706b6c0f7c03',
        [
            '/api/gen/**/*.py',
            '/api/__init__.py',
            '/third_party/infra_libs/*',
            '/third_party/six/*',
            '/third_party/google/api/*',
            '/third_party/google/rpc/*',
            '/third_party/__init__.py',
            '/__init__.py',
            '!*test.py',
        ],
        fixup_chromite_imports,
    ),
    _GitDep('luci', 'https://chromium.googlesource.com/infra/luci/luci-py',
            '33a910c714948a5189f9c58101ce9b131f01c1fd', [
                '/appengine/components/components/auth/**/*.py',
                '/appengine/components/components/datastore_utils/**/*.py',
                '/appengine/components/components/prpc/**/*.py',
                '/appengine/components/components/*.py',
                '!*test.py',
            ], None),
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

    if dep.post_process:
      dep.post_process()


def _set_sparse_checkout_paths(checkout_dir, sparse_checkout_paths):
  """Set the path patterns to checkout in a git checkout."""
  # Pass in path patterns via stdin to avoid shell escaping issues.
  proc = subprocess.Popen(['git', 'sparse-checkout', 'set', '--no-cone', '--stdin'],
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
