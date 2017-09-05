# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for interacting with MySQL database, like cidb."""
# pylint: disable=g-bad-import-order

import MySQLdb
import collections
import logging
import os

import config_reader
import constants
import file_getter
import time_converter

BuildInfo = collections.namedtuple(
    'BuildInfo',
    [
        'board',
        'milestone',
        'platform',
        'build_config',
    ])


class DBConnection(object):
  """The class for reading ChromeOS lab's db."""

  def __init__(self, db_tag, db_name):
    """Initialize a MySQLdb reader.

    Args:
      db_tag: a string section name in db config file, e.g.
        credentials/cloud_sql_credentials.txt, to get db connection info.
      db_name: the database to use.
    """
    self._db_tag = db_tag
    self._read_credentials()
    self._db = self.connect_to_cloudsql()
    self._cursor = self._db.cursor()

    self._db_name = db_name
    if self._db_name:
      self._select_db(self._db_name)

  @property
  def cursor(self):
    return self._cursor

  @property
  def db(self):
    return self._db

  def connect_to_cloudsql(self):
    """Connect to cloudsql by socket or tcp."""
    cur_env = constants.environment()
    if (cur_env == constants.RunningEnv.ENV_DEVELOPMENT_SERVER or
        cur_env == constants.RunningEnv.ENV_PROD):
      # Running on local development server or app engine
      # Connect using the unix socket located at
      # /cloudsql/cloudsql-connection-name.
      cloudsql_unix_socket = os.path.join(
          '/cloudsql', self._connection_name)

      db = MySQLdb.connect(
          unix_socket=cloudsql_unix_socket,
          user=self._user,
          passwd=self._pw)

    # If the unix socket is unavailable, then try to connect using TCP.
    # This will work if you're running a local MySQL server or using the
    # Cloud SQL proxy, for example:
    #
    #   $ cloud_sql_proxy -instances=your-connection-name=tcp:3306
    #
    else:
      db = MySQLdb.connect(
          host='127.0.0.1', user=self._user, passwd=self._pw)

    return db

  def _read_credentials(self):
    """Read credentials from credentials_path."""
    db_config = config_reader.DBConfig(
        config_reader.ConfigReader(file_getter.SQL_CREDENTIAL_FILE))
    configs = db_config.get_credentials(self._db_tag)
    self._connection_name = configs.connection_name
    self._user = configs.user
    self._pw = configs.password

  def _select_db(self, db_name):
    self._cursor.execute('USE %s' % db_name)


class CIDBClient(object):
  """class for interacting with CIDB."""

  def __init__(self, db_tag, db_name):
    """Initialize a cidb reader."""
    self._connection = DBConnection(db_tag, db_name)

  def get_passed_builds_since_date(self, since_date):
    """Get passed builds since a given date.

    Args:
      since_date: a date string, like '2017-02-01 23:00:00'.

    Returns:
      A list of BuildInfo objects.

    Raises:
      MySQLdb.OperationalError if connection operations are not valid.
    """

    sql = """\
        select bo.board, bu.milestone_version,
        bu.platform_version, bu.build_config
        from buildTable as bu, boardPerBuildTable as bo
        where bu.status='pass' and bu.suite_scheduling=1 and
        bu.finish_time > %s and bu.id=bo.build_id
    """
    logging.info('Get passed builds since %r', since_date)
    self._connection.cursor.execute(
        sql, [since_date.strftime(time_converter.TIME_FORMAT)])
    builds = self._connection.cursor.fetchall()
    return [BuildInfo(board, milestone, platform, build_config)
            for board, milestone, platform, build_config in builds]

  def get_latest_passed_builds(self, build_config):
    """Get latest passed builds by build_config.

    Args:
      build_config: format like '{board}-{build_type}', eg. link-release

    Returns:
      A BuildInfo object, represents the latest passed build.

    Raises:
      MySQLdb.OperationalError if connection operations are not valid.
    """
    sql = """\
        select bo.board, bu.milestone_version, bu.platform_version
        from buildTable as bu, boardPerBuildTable as bo
        where bu.build_config=%s and bu.status='pass' and
        bu.id=bo.build_id order by finish_time desc limit 1
    """
    self._connection.cursor.execute(sql, [build_config])
    version_info = self._connection.cursor.fetchall()
    if not version_info:
      return None
    else:
      return BuildInfo(board=version_info[0][0],
                       milestone=version_info[0][1],
                       platform=version_info[0][2],
                       build_config=build_config)
