# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module of config file readers."""
# pylint: disable=invalid-name

import collections
import ConfigParser
import re

import build_utils


# Namedtuple for storing db info.
DBInfo = collections.namedtuple(
    'DBConfigs',
    [
        'connection_name',
        'user',
        'password',
    ])

# Config readers.
Configs = collections.namedtuple(
    'Configs',
    [
        'lab_config',
        'migration_config',
    ])

# The entries of android settings in lab config file.
ANDROID_SETTINGS = 'ANDROID'

# The entries of CrOS settings in lab config file.
CROS_SETTINGS = 'CROS'

# The entries of Skylab settings in migration config file.
SKYLAB_SETTINGS = 'SKYLAB'

# The entry of release ro builds in lab config file.
RELEASED_RO_BUILDS = 'RELEASED_RO_BUILDS'


def forgive_config_error(func):
  """A decorator making ConfigParser get*() functions return None on fail."""
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except ConfigParser.Error:
      return None

  return wrapper


class ConfigReader(ConfigParser.SafeConfigParser):
  """A SafeConfigReader that returns None on any error in get*().

  TODO(xixuan): This config_reader uses ConfigParser class to read config
  file. This config format could be replaced by other more expressive ones.
  """

  def __init__(self, filename):
    """Initialize a config reader."""
    ConfigParser.SafeConfigParser.__init__(self)
    self.read(filename)

  def read(self, filename):
    """Read the file indicated by the given filename.

    Args:
      filename: string for the file name to read.
    """
    self.filename = filename
    if filename is not None:
      ConfigParser.SafeConfigParser.read(self, filename)

  @forgive_config_error
  def getstring(self, section, option):
    """Get string value for the given section and option."""
    return ConfigParser.SafeConfigParser.get(self, section, option)

  @forgive_config_error
  def getint(self, section, option):
    """Get int value for the given section and option."""
    return ConfigParser.SafeConfigParser.getint(self, section, option)

  @forgive_config_error
  def getfloat(self, section, option):
    """Get float value for the given section and option."""
    return ConfigParser.SafeConfigParser.getfloat(self, section, option)

  @forgive_config_error
  def getboolean(self, section, option):
    """Get boolean value for the given section and option."""
    return ConfigParser.SafeConfigParser.getboolean(self, section, option)


class LabConfig(object):
  """Class for reading lab config file for suite scheduler."""

  def __init__(self, config_reader):
    """Initialize a LabConfig to read lab info.

    Args:
      config_reader: a ConfigReader to read lab configs.
    """
    self._config_reader = config_reader

  def get_dedicated_afe(self):
    return self._config_reader.getstring(CROS_SETTINGS, 'afe_server')

  def get_android_board_list(self):
    """Get the android board list from lab config file.

    Returns:
      A set of Android boards: (android-angler, android-bullhead, ...)

    Raises:
      ValueError: no android board list is found.
    """
    board_list = self._config_reader.getstring(
        ANDROID_SETTINGS, 'board_list')
    if board_list is None:
      raise ValueError('Cannot find Android board_list in lab config file.')

    return set([re.match(r'(.*?)(?:-\d+)?$', board.strip()).group(1)
                for board in board_list.split(',')])

  def get_cros_board_list(self):
    """Get the CrOS board list from lab config file.

    Returns:
      A set of CrOS boards: (abox_edge, alex, ...)

    Raises:
      ValueError: no CrOS board list is found.
    """
    board_list = self._config_reader.getstring(CROS_SETTINGS, 'board_list')
    if board_list is None:
      raise ValueError('Cannot find CrOS board_list in lab config file.')

    android_board_list = self.get_android_board_list()
    # Filter board like xxxx_1 to xxxx.
    cros_board_list = set([re.match(r'(.*?)(?:-\d+)?$', board.strip()).group(1)
                           for board in board_list.split(',')])
    return cros_board_list - android_board_list

  def get_cros_model_map(self):
    """Gets a map of CrOS boards onto a list of their corresponding models.

    Returns:
      A map of CrOS board names onto a list of models
    """
    result = {}
    if not self._config_reader:
      return result

    encoded_map = self._config_reader.getstring(CROS_SETTINGS, 'model_list')
    if encoded_map is None:
      return result

    # Models are encoded in form boardName_modelName
    for full_model in encoded_map.split(','):
      board_name, model_name = build_utils.parse_full_model(full_model)
      if board_name in result:
        result[board_name].append(model_name)
      else:
        result[board_name] = [model_name]

    return result

  def get_firmware_ro_build_list(self, release_board):
    """Get firmware ro build list from config file.

    Args:
      release_board: The format like RELEASED_RO_BUILDS_[board].

    Returns:
      a string contains released_ro_builds split by comma.

    Raises:
      ValueError: if no firmware_ro_build found.
    """
    board_list = self._config_reader.getstring(
        RELEASED_RO_BUILDS, release_board)
    if board_list is None:
      raise ValueError('No firmware ro build list found for %s' %
                       release_board)

    return board_list


class MigrationConfig(object):
  """Class for reading migration config file for suite scheduler."""

  def __init__(self, config_reader):
    """Initialize a MigrationConfig to read migration info.

    Args:
      config_reader: a ConfigReader object to read migration configs.
    """
    self._config_reader = config_reader

  def get_skylab_model_list(self):
    """Get the skylab model map from migration config file.

    Returns:
      A set of CrOS models which should be scheduled on skylab:
        (nyan_blaze, reef, ...)
    """
    if not self._config_reader:
      return set([])

    skylab_model_list = self._config_reader.getstring(
        SKYLAB_SETTINGS, 'model_list')
    if skylab_model_list is None:
      return set([])

    return set([re.match(r'(.*?)(?:-\d+)?$', model.strip()).group(1)
                for model in skylab_model_list.split(',')])

  def get_skylab_suite_list(self):
    """Get the skylab suite list from migration config file.

    Returns:
      A set of CrOS suites which should be scheduled on skylab:
        (ent-nightly, ent-perbuild, ...)
    """
    if not self._config_reader:
      return set([])

    skylab_suite_list = self._config_reader.getstring(
        SKYLAB_SETTINGS, 'suite_list')
    if skylab_suite_list is None:
      return set([])

    return set([suite.strip() for suite in skylab_suite_list.split(',')])


class DBConfig(object):
  """Class for reading db config file for suite scheduler."""

  def __init__(self, config_reader):
    """Initialize a DBConfig to read db info.

    Args:
      config_reader: a config reader to read task config.
    """
    self._config_reader = config_reader

  def get_credentials(self, db_tag):
    """Get cidb connection name/user/passwd.

    Args:
      db_tag: the section to read credentials.

    Returns:
      A DBInfo object.
    """
    return DBInfo(
        connection_name=self._config_reader.getstring(
            db_tag, 'connection_name'),
        user=self._config_reader.getstring(db_tag, 'user'),
        password=self._config_reader.getstring(db_tag, 'password'))
