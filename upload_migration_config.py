# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The script to upload migration configs."""
# pylint: disable=g-import-not-at-top


from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import os
import sys

import gae_import


def _make_parser():
  """Return a script runner parser."""
  parser = argparse.ArgumentParser(
      description=__doc__,
      formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument(
      '--sdk_path',
      help='The path of Google App Engine SDK and Google Cloud SDK.',
      default=gae_import.GOOGLE_CLOUD_SDK_PATH)
  parser.add_argument(
      '--dest_bucket',
      help='The Google storage bucket to upload.',
      default='')
  return parser


def run(dest_bucket):
  """Main function."""
  import constants
  import file_getter
  import rest_client
  import setup_environment
  if not os.path.exists(file_getter.STAGING_CLIENT_SECRETS_FILE):
    print('Downloading credentials from %s' % setup_environment.CREDS_GS_PATH)
    setup_environment.fetch_service_credentials(force_update_cred=True)

  storage_client = rest_client.StorageRestClient(
      rest_client.BaseRestClient(
          constants.RestClient.STORAGE_CLIENT.scopes,
          constants.RestClient.STORAGE_CLIENT.service_name,
          constants.RestClient.STORAGE_CLIENT.service_version))

  dest_object_path = os.path.basename(file_getter.MIGRATION_CONFIG_FILE)
  if not dest_bucket:
    dest_bucket = constants.StorageBucket.PROD_SUITE_SCHEDULER

  res = storage_client.upload_object(
      dest_bucket,
      src_object_path=file_getter.MIGRATION_CONFIG_FILE,
      dest_object_path=dest_object_path)

  print('###### Uploaded Successfully ######')
  for k, v in res.iteritems():
    print('%s: %s' % (k, v))


def main():
  """Entry point."""
  upload_parser = _make_parser()
  args = upload_parser.parse_args()

  # Import Google appengine sdk and configs.
  gae_import.import_sdk_path(args.sdk_path)
  gae_import.import_appengine_config()
  run(args.dest_bucket)


if __name__ == '__main__':
  sys.exit(main())
