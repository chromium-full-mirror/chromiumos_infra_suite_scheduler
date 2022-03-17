# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for task config reader unittests."""
# pylint: disable=g-missing-super-call

import unittest

import config_reader


class LabReaderTestCase(unittest.TestCase):

  def setUp(self):
    self.config = config_reader.ConfigReader(None)
    self.config.add_section(config_reader.ANDROID_SETTINGS)
    self.config.add_section(config_reader.CROS_SETTINGS)

  def testGetAndroidBoardList(self):
    """Ensure android board list can be correctly fetched."""
    self.config.set(config_reader.ANDROID_SETTINGS, 'board_list',
                    '\nabox_edge,\nandroid-angler-1,\nangler-6')
    lab_config = config_reader.LabConfig(self.config)
    self.assertEqual(lab_config.get_android_board_list(),
                     set([]))

  def testGetCrOSBoardList(self):
    """Ensure android board list can be correctly fetched."""
    self.config.set(config_reader.CROS_SETTINGS, 'board_list',
                    '\nlink')
    lab_config = config_reader.LabConfig(self.config)
    self.assertEqual(lab_config.get_cros_board_list(),
                     set(['link']))

  def testGetCrOSModelMap(self):
    """Ensure cros_model_map can be correctly fetched."""
    self.config.set(config_reader.CROS_SETTINGS, 'model_list',
                    '\ncoral_astronaut,\ncoral_robo360')
    lab_config = config_reader.LabConfig(self.config)
    result = lab_config.get_cros_model_map()
    self.assertEqual(len(result), 1)
    self.assertEqual(result['coral'], ['astronaut', 'robo360'])

  def testGetEmptyCrOSModelMap(self):
    """Ensure cros_model_map can be correctly fetched."""
    lab_config = config_reader.LabConfig(self.config)
    self.assertEqual(lab_config.get_cros_model_map(), {})

  def testGetAndroidModelMap(self):
    """Ensure android_model_map can be correctly fetched."""
    self.config.set(config_reader.ANDROID_SETTINGS, 'model_list',
                    '\npixel3_pixel3xl,\npixel3_pixel3a,\npixel4_pixel4a')
    lab_config = config_reader.LabConfig(self.config)
    expected = {'pixel3': ['pixel3xl', 'pixel3a'],
                'pixel4': ['pixel4a']}
    actual = lab_config.get_android_model_map()
    self.assertEqual(len(actual), 2)
    self.assertEqual(actual, expected)


class RubikReaderTestCase(unittest.TestCase):

  def setUp(self):
    self.config = config_reader.ConfigReader(None)
    self.config.add_section(config_reader.RUBIK_SETTINGS)

  def testGetRubikBuildTargetList(self):
    """Ensure Rubik build target list can be correctly fetched."""
    self.config.set(config_reader.RUBIK_SETTINGS, 'build_target_list',
                    '\natlas-kernelnext,\neve')
    rubik_config = config_reader.RubikConfig(self.config)
    self.assertEqual(rubik_config.get_build_target_list(),
                     set(['atlas-kernelnext', 'eve']))


if __name__ == '__main__':
  unittest.main()
