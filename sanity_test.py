# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for sanity tests."""

import unittest

import config_reader
import file_getter


class ConfigSanityTest(unittest.TestCase):

  def testSuiteSchedulerINI(self):
    suite_config_file = file_getter.SUITE_SCHEDULER_CONFIG_FILE
    task_config = config_reader.TaskConfig(
        config_reader.ConfigReader(suite_config_file))

    exceptions = []
    for keyword in config_reader.EVENT_CLASSES.keys():
      response = task_config.get_tasks_by_keyword(keyword)
      if response['exceptions']:
        exceptions.extend(response['exceptions'])

    if exceptions:
      self.fail('Fail sanity check for %s:\n%s' % (
          suite_config_file, '\n'.join(exceptions)))

  def testLabConfigParse(self):
    reader = config_reader.LabConfig(
        config_reader.ConfigReader(file_getter.LAB_CONFIG_FILE))
    self.assertGreater(len(reader.get_skylab_board_list()), 0)
    self.assertGreater(len(reader.get_skylab_suite_list()), 0)
    self.assertGreater(len(reader.get_skylab_model_map()), 0)
    self.assertGreater(len(reader.get_cros_model_map()), 0)

  def testLabConfigModels(self):
    reader = config_reader.LabConfig(
        config_reader.ConfigReader(file_getter.LAB_CONFIG_FILE))
    boards = set(reader.get_cros_board_list())
    model_map = reader.get_cros_model_map()
    skylab_boards = set(reader.get_skylab_board_list())
    skylab_model_map = reader.get_skylab_model_map()

    self.assertLessEqual(set(model_map.keys()), boards)
    self.assertLessEqual(set(skylab_model_map.keys()), skylab_boards)

    self.assertLessEqual(skylab_boards, boards)
    self.assertLessEqual(
        set(skylab_model_map.keys()),
        set(model_map.keys()),
    )
    for sk_board, sk_models in skylab_model_map.iteritems():
      self.assertLessEqual(set(sk_models), set(model_map[sk_board]))


if __name__ == '__main__':
  unittest.main()
