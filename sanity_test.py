# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Module for sanity tests."""

import ConfigParser
import unittest

import build_lib
import config_reader
import file_getter
import task_config_reader

from chromite.api.gen.test_platform import request_pb2 as ctp_request

def _priority_is_valid(t):
  """A helper to verify the configured priority."""
  if t.priority is None:
    return True
  return 50 <= t.priority <= 255


def _get_lab_config():
  """A helper to get the boards and models from the lab_config.ini."""
  reader = config_reader.LabConfig(
      config_reader.ConfigReader(file_getter.LAB_CONFIG_FILE))
  boards = set(reader.get_cros_board_list())
  model_map = reader.get_cros_model_map()
  return (boards, model_map)


def _get_model_list(boards, model_map):
  """Get model list for specific boards.

  Args:
    boards: A string list of boards.
    model_map: A dict object maps board(key) and its model list(value).

  Returns:
    A string list of models in suite scheduler pattern,
      e.g. [kukui_krane, grunt_treeya].
  """
  res = []
  for b in boards:
    # Remove the suffix if the board has, e.g. kefka-kernelnext.
    lab_board = build_lib.reshape_board(b)
    for m in model_map.get(lab_board, [None]):
      if m:
        res.append(lab_board + '_' + m)
  return res


class RawConfigReader(ConfigParser.RawConfigParser):
  """A RawConfigReader that returns error for duplicate section name."""
  def __init__(self, filename):
    """Initialize a config reader."""
    ConfigParser.RawConfigParser.__init__(self)
    self.read(filename)

  def read(self, filename):
    """Read the file indicated by the given filename.

    Args:
      filename: string for the file name to read.
    """
    self.filename = filename
    if filename is not None:
      ConfigParser.RawConfigParser.read(self, filename)


class ConfigSanityTest(unittest.TestCase):

  def _is_valid_migration(self, name):
    if not hasattr(self, "_migration_names"):
      # Get a list of permissible migration names, as strings
      descriptor = ctp_request.Request.Params.Migrations.DESCRIPTOR
      self._migration_names = set(descriptor.fields_by_name.keys())
    return name in self._migration_names

  def testLabConfigParse(self):
    reader = config_reader.LabConfig(
        config_reader.ConfigReader(file_getter.LAB_CONFIG_FILE))
    self.assertGreater(len(reader.get_cros_model_map()), 0)

  def testLabConfigModels(self):
    b, m = _get_lab_config()
    self.assertLessEqual(set(m.keys()), b)

  def testSuiteCongigSectionName(self):
    suite_config_file = file_getter.SUITE_SCHEDULER_CONFIG_FILE
    try:
      task_config_reader.TaskConfig(RawConfigReader(suite_config_file),
                                    is_sanity=True)
    except ConfigParser.DuplicateSectionError as e:
      self.fail('Duplicate section name: %s' % str(e))

  def testSuiteSchedulerINI(self):
    suite_config_file = file_getter.SUITE_SCHEDULER_CONFIG_FILE
    task_config = task_config_reader.TaskConfig(
        config_reader.ConfigReader(suite_config_file), is_sanity=True)
    exceptions = []
    lab_boards, lab_model_map = _get_lab_config()
    lab_possible_models = _get_model_list(lab_boards, lab_model_map)
    for keyword in task_config_reader.EVENT_CLASSES.keys():
      response = task_config.get_tasks_by_keyword(keyword)
      if response['exceptions']:
        exceptions.extend(response['exceptions'])
      for t in response['tasks']:
        possible_models = lab_possible_models
        if t.boards:
          for board in t.boards:
            if board not in lab_boards:
              exceptions.append('Task %s has unknown board %s.' %
                                (t.name, board))
              continue
          # If the task has a set of boards, only the models belonging
          # to these boards can be added to the "models" field.
          possible_models = _get_model_list(t.boards, lab_model_map)
        if t.models:
          for model in t.models:
            if model not in lab_possible_models:
              exceptions.append('Task %s has unknown model %s.' %
                                (t.name, model))
              continue
            if model not in possible_models:
              exceptions.append(
                  'Task %s has unschedulable model %s. It does not '
                  'belongs to the boards already configured for '
                  'this task.' % (t.name, model))

        if not _priority_is_valid(t):
          exceptions.append(
              'Task %s has invalid priority %d: the valid range is [50, 255].'
              % (t.name, t.priority))
        if t.dimensions is not None:
          for label in t.dimensions.split(','):
            if len(label.split(':')) != 2:
              exceptions.append(
                  'Task %s has invalid dimension %s: '
                  'only dimensions of the form key:value are allowed' %
                  (t.name, label))
        if t.pool == 'suites' and t.priority:
          exceptions.append(
              'Task %s is in suite pool, and should not have priority, %d.' %
              (t.name, t.priority))
        if t.qs_account and t.priority:
          exceptions.append(
              'Task %s should not have both quota account and priority '
              'configured.' % t.name)
        if t.migrations:
          for m in t.migrations:
            if not self._is_valid_migration(m):
              exceptions.append('Task %s has invalid migration %s enabled' %
                                (t.name, m))

    if exceptions:
      self.fail('Fail sanity check for %s:\n%s' %
                (suite_config_file, '\n'.join(exceptions)))


if __name__ == '__main__':
  unittest.main()
