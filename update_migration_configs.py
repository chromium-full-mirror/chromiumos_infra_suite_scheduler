# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The script to dump migration configs.

It's used to generate json file configs/dump_migration.json based on
configs/migration_config.ini.
"""
# pylint: disable=g-import-not-at-top


from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
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
  return parser


def run():
  """Main function."""
  import config_reader
  import file_getter
  migration_config = config_reader.MigrationConfig(
      config_reader.ConfigReader(file_getter.MIGRATION_CONFIG_FILE))
  res = migration_config.get_skylab_suites_dump()
  with open(file_getter.MIGRATION_CONFIG_JSON, 'w') as f:
    f.write(config_reader.config_dump(res))

  print('Successfully dumped to %s.' % file_getter.MIGRATION_CONFIG_JSON)


def main():
  """Entry point."""
  upload_parser = _make_parser()
  args = upload_parser.parse_args()

  # Import Google appengine sdk and configs.
  gae_import.import_sdk_path(args.sdk_path)
  gae_import.import_appengine_config()
  run()


if __name__ == '__main__':
  sys.exit(main())
