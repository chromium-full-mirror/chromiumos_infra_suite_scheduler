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
      for t in response['tasks']:
        if t.dimensions is not None:
          for label in t.dimensions.split(','):
            if len(label.split(':')) != 2:
              self.fail('Fail sanity check for dimensions %s.' % t.dimensions)

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


if __name__ == '__main__':
  unittest.main()
