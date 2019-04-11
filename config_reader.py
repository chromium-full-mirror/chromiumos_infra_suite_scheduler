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

# The entries of override settings in migration config file.
OVERRIDE_SETTINGS = 'OVERRIDE'
# The key of override info dict.
OVERRIDE_POOL = 'override_pool'
OVERRIDE_QS_ACCOUNT = 'override_qs_account'

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

  def get_override_mappings(self, pool, model):
    """Get the override info from migration config file.

    Args:
      pool: A string pool name
      model: A string model name

    Returns:
      A dict of override info, including override_pool and override_account.
    """
    if not self._config_reader:
      return {}

    override_mappings = self._config_reader.getstring(OVERRIDE_SETTINGS,
                                                      _pool_model_key(pool))
    if override_mappings is None:
      override_mappings = self._config_reader.getstring(
          OVERRIDE_SETTINGS, _pool_model_key(pool, model))

    if override_mappings is None:
      return {OVERRIDE_POOL: '', OVERRIDE_QS_ACCOUNT: ''}

    return {OVERRIDE_POOL: override_mappings.split(',')[0].strip(" '"),
            OVERRIDE_QS_ACCOUNT: override_mappings.split(',')[1].strip(" '")}

  def get_skylab_pools(self):
    if not self._config_reader:
      return []

    skylab_pools = self._config_reader.getstring(SKYLAB_SETTINGS, 'pools')
    if skylab_pools is None:
      return []

    return [p.strip() for p in skylab_pools.split(',')]

  def get_skylab_models_by_pool(self, pool):
    """Get a model list in skylab from migration config file.

    Args:
      pool: A string pool name

    Returns:
      A list of CrOS models for the given pool which should be scheduled on
      skylab:
        e.g. ['astronaut', 'reef', ...]
    """
    models = self._config_reader.getstring(SKYLAB_SETTINGS, pool)
    if models is None:
      return []

    return list(_parse_model_list(models))

  def get_skylab_suites_dump(self):
    """Get a dict of configs for skylab suites.

    Returns:
      A dict to contain skylab suite configs.
    """
    result = collections.defaultdict(dict)

    suites = self._config_reader.sections()
    for s in suites:
      if s in [SKYLAB_SETTINGS, OVERRIDE_SETTINGS]:
        continue

      pools = self._config_reader.getstring(s, 'pools')
      if not pools:
        raise ValueError('Need to specify "pools" for suite %s' % s)

      pools = list(set([p.strip() for p in pools.split(',')]))

      whitelist = _parse_pool_list(
          self._config_reader.getstring(s, 'whitelist'))
      blacklist = _parse_pool_list(
          self._config_reader.getstring(s, 'blacklist'))

      result[suite_key(s)] = self._get_configs_for_suite(
          pools, whitelist, blacklist)

    return result

  def _get_configs_for_suite(self, pool_list, whitelist, blacklist):
    """Get migration configs for a suite.

    Args:
      pool_list: A list of string pool.
        e.g. ('cq', 'bvt', ...)
      whitelist: A list of whitelist pool/model combinations, in the form
        'pool:model'. Suites for these will run in skylab.
        e.g. ['cq:astronaut', 'bvt:peppy', ...]
      blacklist: A set of blacklisted pool/model combinations,
        in the same form as whitelist.

    Returns:
      A dict containing migration configs for a given suite, e.g.
      {
          'pool:cq': {
              model:astronaut: {
                  skylab: True,
                  override_pool: '',
                  override_qs_account: '',
              }
          }
          'pool:bvt': {
              'model:peppy': {
                  skylab: True,
                  override_pool: DUT_POOL_QUOTA,
                  override_qs_account: xxx,
              }
              'model:link': {
                  ...,
              }
          }
          ...
      }
    """
    result = {}
    for pool in pool_list:
      skylab_models = self.get_skylab_models_by_pool(pool)
      white_models = _get_models_by_pool(whitelist, pool)
      if white_models:
        result[pool_key(pool)] = self._get_configs_for_models(pool,
                                                              white_models)
        continue

      black_models = _get_models_by_pool(blacklist, pool)
      result[pool_key(pool)] = self._get_configs_for_models(
          pool,
          list(set(skylab_models) - set(black_models)))

    return result

  def _get_configs_for_models(self, pool, white_models):
    """Get configs for a list of models.

    Args:
      pool: A string pool name.
      white_models: A list of string models. e.g.
        ['peppy', 'link', ...]

    Returns:
      A dict containing migration configs of models. e.g.
        {
            'peppy': {
                skylab: True,
                override_pool: DUT_POOL_QUOTA,
                override_account: '',
            }
            'link':  {
                ...,
            }
        }
    """
    result = {}
    for m in white_models:
      result[model_key(m)] = {'skylab': True}
      result[model_key(m)].update(self.get_override_mappings(pool, m))

    return result


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
