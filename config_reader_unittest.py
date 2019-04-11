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
    self.config.add_section(config_reader.RELEASED_RO_BUILDS)

  def testGetAndroidBoardList(self):
    """Ensure android board list can be correctly fetched."""
    self.config.set(config_reader.ANDROID_SETTINGS, 'board_list',
                    '\nabox_edge,\nandroid-angler-1,\nangler-6')
    lab_config = config_reader.LabConfig(self.config)
    self.assertEqual(lab_config.get_android_board_list(),
                     set(['abox_edge', 'android-angler', 'angler']))

  def testGetInvalidAndroidBoardListEntry(self):
    """Ensure ValueError is raised if no valid board list entry."""
    self.config.set(config_reader.ANDROID_SETTINGS, 'invalid_board_list',
                    '\nabox_edge,\nandroid-angler-1,\nangler-6')
    lab_config = config_reader.LabConfig(self.config)
    self.assertRaises(ValueError, lab_config.get_android_board_list)

  def testGetEmptyAndroidBoardListEntry(self):
    """Ensure ValueError is raised if no android board list is found."""
    lab_config = config_reader.LabConfig(self.config)
    self.assertRaises(ValueError, lab_config.get_android_board_list)

  def testGetCrOSBoardList(self):
    """Ensure android board list can be correctly fetched."""
    self.config.set(config_reader.CROS_SETTINGS, 'board_list',
                    '\nlink,\nandroid-angler-1,\nangler-6')
    self.config.set(config_reader.ANDROID_SETTINGS, 'board_list',
                    '\nandroid-angler-1,\nangler-6')
    lab_config = config_reader.LabConfig(self.config)
    self.assertEqual(lab_config.get_cros_board_list(),
                     set(['link']))

  def testGetFirmwareROBuildList(self):
    """Ensure firmware ro build can be successfully found."""
    self.config.set(config_reader.RELEASED_RO_BUILDS, 'link', 'firmware')
    lab_config = config_reader.LabConfig(self.config)
    self.assertEqual(lab_config.get_firmware_ro_build_list('link'),
                     'firmware')

  def testGetEmptyFirmwareROBuildList(self):
    """Ensure ValueError is raised if no firmware ro build is found."""
    lab_config = config_reader.LabConfig(self.config)
    self.assertRaises(ValueError,
                      lab_config.get_firmware_ro_build_list, 'link')

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


class MigrationReaderTestCase(unittest.TestCase):

  def setUp(self):
    self.config = config_reader.ConfigReader(None)
    self.config.add_section(config_reader.SKYLAB_SETTINGS)

  def testGetSkylabSuites(self):
    """Ensure suites in skylab can be correctly fetched."""
    suite_name = 'fake_suite'
    self.config.set(config_reader.SKYLAB_SETTINGS, 'pools',
                    '\ncq')
    self.config.set(config_reader.SKYLAB_SETTINGS, 'cq',
                    '\nreef,\nrobo360')
    self.config.add_section(suite_name)
    self.config.set(suite_name, 'pools', '\ncq')
    config = config_reader.MigrationConfig(self.config)
    result = config.get_skylab_suites_dump()
    self.assertEqual(len(result), 1)

    sk = config_reader.suite_key(suite_name)
    pk = config_reader.pool_key('cq')
    self.assertIn(sk, result)
    self.assertIn(config_reader.pool_key('cq'), result[sk])
    self.assertIn(config_reader.model_key('reef'), result[sk][pk])
    self.assertIn(config_reader.model_key('robo360'), result[sk][pk])

  def testGetSkylabSuitesWhitelistFirst(self):
    """Ensure whitelist goes first in migration config parsing."""
    suite_name = 'fake_suite'
    self.config.set(config_reader.SKYLAB_SETTINGS, 'pools',
                    '\ncq')
    self.config.set(config_reader.SKYLAB_SETTINGS, 'cq',
                    '\nreef,\nrobo360')
    self.config.add_section(suite_name)
    self.config.set(suite_name, 'pools', '\ncq')
    self.config.set(suite_name, 'whitelist', '\n(cq, peppy)\n(cq, reef)')
    config = config_reader.MigrationConfig(self.config)
    result = config.get_skylab_suites_dump()

    sk = config_reader.suite_key(suite_name)
    pk = config_reader.pool_key('cq')
    self.assertEqual(len(result), 1)
    self.assertIn(sk, result)
    self.assertIn(pk, result[sk])
    self.assertIn(config_reader.model_key('reef'), result[sk][pk])
    self.assertNotIn(config_reader.model_key('robo360'), result[sk][pk])
    self.assertIn(config_reader.model_key('peppy'), result[sk][pk])

  def testGetSkylabSuitesBlacklist(self):
    """Ensure blacklist is blocked in migration config parsing."""
    suite_name = 'fake_suite'
    self.config.set(config_reader.SKYLAB_SETTINGS, 'pools',
                    '\ncq')
    self.config.set(config_reader.SKYLAB_SETTINGS, 'cq',
                    '\nreef,\nrobo360')
    self.config.add_section(suite_name)
    self.config.set(suite_name, 'pools', '\ncq')
    self.config.set(suite_name, 'blacklist', '\n(cq, reef)')
    config = config_reader.MigrationConfig(self.config)
    result = config.get_skylab_suites_dump()

    sk = config_reader.suite_key(suite_name)
    pk = config_reader.pool_key('cq')
    self.assertEqual(len(result), 1)
    self.assertIn(sk, result)
    self.assertIn(pk, result[sk])
    self.assertNotIn(config_reader.model_key('reef'), result[sk][pk])
    self.assertIn(config_reader.model_key('robo360'), result[sk][pk])


if __name__ == '__main__':
  unittest.main()
