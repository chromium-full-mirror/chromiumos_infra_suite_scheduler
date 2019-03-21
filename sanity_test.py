# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for sanity tests."""

import unittest

import config_reader
import file_getter
import task_config_reader


class ConfigSanityTest(unittest.TestCase):

  def testSuiteSchedulerINI(self):
    suite_config_file = file_getter.SUITE_SCHEDULER_CONFIG_FILE
    task_config = task_config_reader.TaskConfig(
        config_reader.ConfigReader(suite_config_file))

    exceptions = []
    for keyword in task_config_reader.EVENT_CLASSES.keys():
      response = task_config.get_tasks_by_keyword(keyword)
      if response['exceptions']:
        exceptions.extend(response['exceptions'])

    if exceptions:
      self.fail('Fail sanity check for %s:\n%s' % (
          suite_config_file, '\n'.join(exceptions)))

  def testLabConfigParse(self):
    reader = config_reader.LabConfig(
        config_reader.ConfigReader(file_getter.LAB_CONFIG_FILE))
    self.assertGreater(len(reader.get_cros_model_map()), 0)

  def testLabConfigModels(self):
    reader = config_reader.LabConfig(
        config_reader.ConfigReader(file_getter.LAB_CONFIG_FILE))
    boards = set(reader.get_cros_board_list())
    model_map = reader.get_cros_model_map()
    self.assertLessEqual(set(model_map.keys()), boards)

  def testMigrationConfigParse(self):
    reader = config_reader.MigrationConfig(
        config_reader.ConfigReader(file_getter.MIGRATION_CONFIG_FILE))
    self.assertGreater(len(reader.get_skylab_pools()), 0)
    self.assertGreater(len(reader.get_skylab_suites_dump()), 0)

  def testMigrationConfigModels(self):
    migration_config = config_reader.MigrationConfig(
        config_reader.ConfigReader(file_getter.MIGRATION_CONFIG_FILE))
    lab_config = config_reader.LabConfig(
        config_reader.ConfigReader(file_getter.LAB_CONFIG_FILE))
    boards = lab_config.get_cros_board_list()
    model_map = lab_config.get_cros_model_map()
    all_models = boards
    for _, v in model_map.iteritems():
      all_models |= set(v)

    skylab_pools = migration_config.get_skylab_pools()
    skylab_model_keys = [config_reader.model_key(m) for m in list(all_models)]
    skylab_pool_keys = [config_reader.pool_key(p) for p in skylab_pools]
    skylab_suites = migration_config.get_skylab_suites_dump()
    for _, sdict in skylab_suites.iteritems():
      included_pools = sdict.keys()
      self.assertLessEqual(set(included_pools), set(skylab_pool_keys))
      for p in sdict.keys():
        self.assertLessEqual(set(sdict[p].keys()), set(skylab_model_keys))


if __name__ == '__main__':
  unittest.main()
