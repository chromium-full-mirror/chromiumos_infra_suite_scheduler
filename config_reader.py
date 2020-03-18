# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module of config file readers."""
# pylint: disable=invalid-name

import collections
import ConfigParser
import json
import re

import build_utils


# Config readers.
Configs = collections.namedtuple(
    'Configs',
    [
        'lab_config',
    ])

# The entries of android settings in lab config file.
ANDROID_SETTINGS = 'ANDROID'

# The entries of CrOS settings in lab config file.
CROS_SETTINGS = 'CROS'

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
  """A SafeConfigReader that returns None on any error in get*()."""

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

    # Models are read from boardName_modelName/familyName_boardName_modelName.
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


def config_dump(res):
  """Dump a config dict to a json string.

  Args:
    res: A dict object to dump.

  Returns:
    A json string.
  """
  return json.dumps(res,
                    sort_keys=True,
                    indent=4,
                    separators=(',', ': ')) + '\n'


def _parse_model_list(models):
  r"""Parse models of list.

  Args:
    models: A string, read from lab or migration config file.
        e.g. '\nreef,\nastronaut,\nrobo360'
  Returns:
    A set of string models, e.g. set(['reef', 'astronaut', 'robo360', ...])
  """
  return set([re.match(r'(.*?)(?:-\d+)?$', m.strip()).group(1)
              for m in models.split(',')])


def _parse_pool_list(l):
  r"""Parse whitelist/blacklist for a suite in migration config file.

  Args:
    l: A string, read from migration config file entry
       whitelist or blacklist. e.g. '\ncq:reef,\nbvt:peppy...'

  Returns:
    A list of whitelist/blacklist <pool:model> string.
    e.g. ['cq:reef', 'bvt:peppy', ...]
  """
  if l is None or not l:
    return []
  else:
    return list(set([w.strip() for w in l.split('\n') if w.strip()]))


def _get_models_by_pool(model_pool_list, pool):
  """Get models from a model_pool_list by pool.

  Args:
    model_pool_list: A list of model_pool string. e.g.
      [(cq, reef), (bvt, peppy), (bvt, link), ...]
    pool: A string pool. e.g. 'bvt'

  Returns:
    A list of string models searched by pool. e.g.
      ['peppy', 'link', ...]
  """
  res = set([])
  for mp in model_pool_list:
    p, m = _parse_pool_model_key(mp)
    if p == pool:
      res.add(m)

  return list(res)


def suite_key(suite_name):
  return 'suite:%s' % suite_name


def model_key(model_name):
  return 'model:%s' % model_name


def pool_key(pool_name):
  return 'pool:%s' % pool_name


def _pool_model_key(pool_name, model_name=None):
  if model_name is None:
    return '(%s)' % pool_name

  return '(%s, %s)' % (pool_name, model_name)


def _parse_pool_model_key(model_pool):
  return (model_pool[1:-1].split(',')[0].strip(),
          model_pool[1:-1].split(',')[1].strip())
