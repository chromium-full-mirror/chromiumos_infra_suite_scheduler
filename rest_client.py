# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for interacting with google APIs."""
# pylint: disable=g-bad-import-order
# pylint: disable=g-bad-exception-name

import ast
import httplib2
import logging
import re

import apiclient
import build_lib
import constants
import file_getter
import global_config
import time_converter

from oauth2client import service_account
from oauth2client.contrib import appengine


class RestClientError(Exception):
  """Raised when there is a general error."""


class NoServiceRestClientError(RestClientError):
  """Raised when there is no ready service for a google API."""


class BaseRestClient(object):
  """Base class of REST client for google APIs."""

  def __init__(self, scopes, service_name, service_version):
    """Initialize a REST client to connect to a google API.

    Args:
      scopes: the scopes of the to-be-connected API.
      service_name: the service name of the to-be-connected API.
      service_version: the service version of the to-be-connected API.
    """
    self.running_env = constants.environment()
    self.scopes = scopes
    self.service_name = service_name
    self.service_version = service_version

  @property
  def service(self):
    if not self._service:
      raise NoServiceRestClientError('No service created for calling API')

    return self._service

  def create_service(self, discovery_url=None):
    """Create the service for a google API."""
    self._init_credentials()
    # Explicitly specify timeout for http to avoid DeadlineExceededError.
    # It's used for services like AndroidBuild API, which raise such error
    # when being triggered too many calls in a short time frame.
    # http://stackoverflow.com/questions/14698119/httpexception-deadline-exceeded-while-waiting-for-http-response-from-url-dead
    http_auth = self._credentials.authorize(httplib2.Http(timeout=30))
    if discovery_url is None:
      self._service = apiclient.discovery.build(
          self.service_name, self.service_version,
          http=http_auth)
    else:
      self._service = apiclient.discovery.build(
          self.service_name, self.service_version, http=http_auth,
          discoveryServiceUrl=discovery_url)

  def _init_credentials(self):
    """Initialize the credentials for a google API."""
    if (self.running_env == constants.RunningEnv.ENV_STANDALONE or
        self.running_env == constants.RunningEnv.ENV_DEVELOPMENT_SERVER):
      # Running locally
      service_credentials = service_account.ServiceAccountCredentials
      self._credentials = service_credentials.from_json_keyfile_name(
          file_getter.STAGING_CLIENT_SECRETS_FILE, self.scopes)
    else:
      # Running in app-engine production
      self._credentials = appengine.AppAssertionCredentials(self.scopes)


class AndroidBuildRestClient(object):
  """REST client for android build API."""

  def __init__(self, rest_client):
    """Initialize a REST client for connecting to Android Build API."""
    self._rest_client = rest_client
    self._rest_client.create_service()

  def get_latest_build_id(self, branch, target):
    """Get the latest build id for a given branch and target.

    Args:
      branch: an android build's branch
      target: an android build's target

    Returns:
      A string representing latest build id.
    """
    request = self._rest_client.service.build().list(
        buildType='submitted',
        branch=branch,
        target=target,
        successful=True,
        maxResults=1)
    builds = request.execute(num_retries=10)
    if not builds or not builds['builds']:
      return None

    return builds['builds'][0]['buildId']


class StorageRestClient(object):
  """REST client for google storage API."""

  def __init__(self, rest_client):
    """Initialize a REST client for connecting to Google storage API."""
    self._rest_client = rest_client
    self._rest_client.create_service()

  def read_object(self, bucket, object_path):
    """Read the contents of input_object in input_bucket.

    Args:
      bucket: A string to indicate the bucket for fetching the object.
        e.g. constants.StorageBucket.PROD_SUITE_SCHEDULER
      object_path: A string to indicate the path of the object to read the
        contents.

    Returns:
      the stripped string contents of the input object.

    Raises:
      apiclient.errors.HttpError
    """
    req = self._rest_client.service.objects().get_media(
        bucket=bucket,
        object=object_path)
    return req.execute()

  def upload_object(self, bucket, src_object_path, dest_object_path):
    """Upload object_path to input_bucket.

    Args:
      bucket: A string to indicate the bucket for the object to be uploaded to.
      src_object_path: A string the full path of the object to upload.
      dest_object_path: A string path inside bucket to upload to.

    Returns:
      A dict of uploaded object info.

    Raises:
      apiclient.errors.HttpError
    """
    req = self._rest_client.service.objects().insert(
        bucket=bucket,
        name=dest_object_path,
        media_body=src_object_path,
        media_mime_type='text/plain',
    )
    return req.execute()


class CalendarRestClient(object):
  """Class of REST client for google calendar API."""

  def __init__(self, rest_client):
    """Initialize a REST client for connecting to Google calendar API."""
    self._rest_client = rest_client
    self._rest_client.create_service()

  def add_event(self, calendar_id, input_event):
    """Add events of a given calendar.

    Args:
      calendar_id: the ID of the given calendar.
      input_event: the event to be added.
    """
    self._rest_client.service.events().insert(
        calendarId=calendar_id,
        body=input_event).execute()


class StackdriverRestClient(object):
  """REST client for google storage API."""

  def __init__(self, rest_client):
    """Initialize a REST client for connecting to Google storage API."""
    self._rest_client = rest_client
    self._rest_client.create_service()

  def read_logs(self, request):
    # project_id, page_size, order_by, query_filter=''):
    """Read the logs of the project_id based on all filters.

    Args:
      request: a request dict generated by
        stackdriver_lib.form_logging_client_request.

    Returns:
      A json object, can be parsed by
        stackdriver_lib.parse_logging_client_response.

    Raises:
      apiclient.errors.HttpError
    """
    req = self._rest_client.service.entries().list(
        fields='entries/protoPayload', body=request)
    return req.execute()


class SwarmingRestClient(object):
  """REST client for swarming proxy API."""

  DISCOVERY_URL_PATTERN = '%s/discovery/v1/apis/%s/%s/rest'

  def __init__(self, rest_client, service_url):
    self._rest_client = rest_client
    discovery_url = self.DISCOVERY_URL_PATTERN % (
        service_url, rest_client.service_name, rest_client.service_version)
    self._rest_client.create_service(discovery_url=discovery_url)

  def create_task(self, request):
    """Create new task.

    Args:
      request: a json-compatible dict expected by swarming server.
        See _to_raw_request's output in swarming_lib.py for details.

    Returns:
      A json dict returned by API task.new.
    """
    return self._rest_client.service.tasks().new(
        fields='request,task_id', body=request).execute()

  def get_task_result(self, task_id):
    """Get task results by a given task_id.

    Args:
        task_id: A string, represents task id.

    Returns:
        A json dict returned by API task.result.
    """
    return self._rest_client.service.task().result(
        task_id=task_id).execute()


class BigqueryRestClient(object):
  """Class of REST client for Bigquery API."""

  PROJECT_TO_RUN_BIGQUERY_JOB = 'google.com:suite-scheduler'

  def __init__(self, rest_client, project=None, dataset=None, table=None):
    """Initialize a REST client for connecting to Bigquery API."""
    self._rest_client = rest_client
    self._rest_client.create_service()
    self.project = project
    self.dataset = dataset
    self.table = table

  def query(self, query_str):
    """Query bigquery.

    Args:
      query_str: A string used to query Bigquery.

    Returns:
      A json dict returned by API bigquery.jobs.query, e.g.
      # {...,
      #  "rows": [
      #     {
      #      "f": [ # field
      #       {
      #        "v": # value
      #       },
      #       {
      #        "v": # value
      #       },
      #       ...
      #      ]
      #     }
      #     ...
      #   ]
      # }
    """
    query_data = {
        'query': query_str,
        'useLegacySql': False,
    }
    return self._rest_client.service.jobs().query(
        projectId=self.PROJECT_TO_RUN_BIGQUERY_JOB,
        fields='rows',
        body=query_data).execute()

  def insert(self, rows):
    """Insert rows to specified Bigquery table.

    Args:
      rows: list of json objects.

    Raise:
      RestClientError: if project/dataset/table is not defined.
    """
    if not any([self.project, self.dataset, self.table]):
      raise RestClientError('Project, dataset, table should be all set.'
                            'Got project:%s, dataset:%s, table:%s' %
                            (self.project, self.dataset, self.table))
    body = {
        'kind': 'bigquery#tableDataInsertAllRequest',
        'rows': rows,
    }
    request = self._rest_client.service.tabledata().insertAll(
        projectId=self.project,
        datasetId=self.dataset,
        tableId=self.table,
        body=body)
    response = request.execute(num_retries=3)
    if response.get('insertErrors'):
      logging.error('InsertRequest reported errors: %r',
                    response.get('insertErrors'))
      return False

    return True

class CrOSTestPlatformBigqueryClient(BigqueryRestClient):
  """REST client for cros_test_platform builder Bigquery API."""

  def get_past_job_nums(self, hours):
    """Query the count of the jobs kicked off to cros_test_platform.

    Args:
      hours: An integer.

    Returns:
      An integer.
    """
    query_str = """
        SELECT
          COUNT(*)
        FROM
          `cr-buildbucket.chromeos.builds`
        WHERE
          created_by = 'user:suite-scheduler.google.com@appspot.gserviceaccount.com'
          and create_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL %d HOUR);
    """
    res = self.query(query_str % hours)
    try:
      return int(_parse_bq_job_query(res)[0][0])
    except (ValueError, KeyError) as e:
      logging.debug('The returned json: \n%r', res)
      logging.exception(str(e))
      raise


class BuildBucketBigqueryClient(BigqueryRestClient):
  """Rest client for buildbucket Bigquery API."""

  def get_latest_passed_firmware_builds(self):
    """Get artifact link of the latest passed firmware builds for board.

    The query returns the latest firmware build for the combination of
    board and build spec, which is cros or firmware. No restriction set
    in the query, so it should return all available builds.

    Returns:
      A list of (spec, board, firmware_artifact_link).
    """
    query_str = """
        SELECT
          spec,
          board,
          /*
          * Firmware builds may contain artifacts for multiple boards in a
          * single build - each in a separate directory.
          */
          IF(spec = 'firmware', CONCAT(artifact, '/', board), artifact) as artifact
        FROM
          (
            SELECT
              spec,
              board,
              artifact,
              RANK() OVER (PARTITION BY spec, board ORDER BY end_time DESC) AS rank
            FROM
              (
                SELECT
                  /*
                  * build_config is a string contains the board and build type.
                  * For Cros build, it has the form of "BoardName-release", while
                  * the firmware config shows like "firmware-BoardName-[1]-firmwarebranch".
                  * [1] is the firmware ver.
                  */
                  IF(prefix = 'firmware', 'firmware', 'cros') AS spec,
                  IF(prefix = 'firmware', firmware_post_prefix, cros_prefix) AS board,
                  artifact,
                  end_time
                FROM
                  (
                    SELECT
                      SPLIT(build_config, '-') [OFFSET(0)] AS prefix,
                      SPLIT(build_config, '-') [OFFSET(1)] AS firmware_post_prefix,
                      REGEXP_EXTRACT(
                        build_config, r"(^[a-zA-Z0-9_.+-]+)-release"
                      ) as cros_prefix,
                      end_time,
                      artifact
                    FROM
                      (
                        SELECT
                          JSON_EXTRACT_SCALAR(
                            output.properties, '$.artifact_link'
                          ) as artifact,
                          JSON_EXTRACT_SCALAR(
                            output.properties, '$.cbb_config'
                          ) as build_config,
                          end_time
                        FROM `cr-buildbucket.chromeos.completed_builds_BETA`
                        WHERE
                          status = 'SUCCESS'
                          AND JSON_EXTRACT_SCALAR(
                            output.properties, '$.suite_scheduling'
                          ) = 'True'
                      )
                  )
              )
          )
        WHERE rank = 1
    """
    res = self.query(query_str)
    res = _parse_bq_job_query(res)
    if res is None:
      return None
    logging.info('Fetched the latest artifact links: %s',
        [row[2] for row in res])
    return res

  def get_passed_builds(self, earliest_end_time, latest_end_time):
    """Get passed builds inside a given time span.

    BigQuery does not guarantee the inserted time of rows. A new build
    may not get inserted when suite scheduler runs the query. To avoid
    it, we run the query twice:
    - the first run catches the new build from earliest_end_time to
      latest_end_time, and inserts the result to a temp BQ table.
    - the second run checks the build from (earliest_end_time - 1Day)
      to (latest_end_time - 1Day) plus (earliest_end_time to
      latest_end_time). The query returns the build which does not
      appear in the temp table. Thus, if a build was not fetched by the
      first run, we still could schedule test on it at most 1 day later.

    Args:
      earliest_end_time: a datetime.datetime object in UTC.
      latest_end_time: a datetime.datetime object in UTC.

    Returns:
      A list of build_lib.BuildInfo objects.
    """
    base_query_str = """
        SELECT
          JSON_EXTRACT_SCALAR(output.properties, '$.board') AS board,
          JSON_EXTRACT_SCALAR(output.properties, '$.milestone_version') AS milestone,
          JSON_EXTRACT_SCALAR(output.properties, '$.platform_version') AS platform,
          JSON_EXTRACT_SCALAR(output.properties, '$.cbb_config') AS build_config,
          -- Time info
          end_time as build_end_time,
          CURRENT_TIMESTAMP() as inserted_time
        FROM
          `cr-buildbucket.chromeos.builds`
        WHERE
          status = 'SUCCESS'
          AND JSON_EXTRACT_SCALAR(output.properties, '$.suite_scheduling') = 'True'
    """

    insert_passed_builds = """
        INSERT
          `google.com:{0}.builds.passed_builds`(
            board,
            milestone,
            platform,
            build_config,
            build_end_time,
            inserted_time
        ) {1}
        AND end_time > '{2}'
        AND end_time < '{3}'
    """
    earliest_end_time_str = earliest_end_time.strftime(
        time_converter.TIME_FORMAT)
    latest_end_time_str = latest_end_time.strftime(
        time_converter.TIME_FORMAT)

    # Insert the currently visible builds to BQ.
    if constants.application_id():
      logging.info('Insert the visible passed builds '
                   'between %s and %s to BQ.',
                   earliest_end_time_str, latest_end_time_str)
      self.query(
          insert_passed_builds.format(
              constants.application_id(),
              base_query_str,
              earliest_end_time_str,
              latest_end_time_str))

    logging.info('Getting passed builds finished between %s and %s',
                 earliest_end_time_str, latest_end_time_str)
    query_str = """
        WITH passed_builds AS
            ({0})
        SELECT
          b.board,
          b.milestone,
          b.platform,
          b.build_config,
        FROM
          passed_builds AS b
        LEFT JOIN
          `google.com:{1}.builds.passed_builds` AS r
          ON (
            r.board = b.board
            AND r.milestone = b.milestone
            AND r.build_config = b.build_config
            AND r.platform = b.platform
            AND r.build_end_time > TIMESTAMP_SUB(
                PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', '{2}'),
                INTERVAL 1 DAY)
            AND r.build_end_time < TIMESTAMP_SUB(
                PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', '{3}'),
                INTERVAL 1 DAY)
          )
        WHERE
          -- Check if any build was inserted to release builder
          -- in the past 24 hours.
          (b.build_end_time > TIMESTAMP_SUB(
              PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', '{2}'),
              INTERVAL 1 DAY)
            AND b.build_end_time < TIMESTAMP_SUB(
                PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', '{3}'),
                INTERVAL 1 DAY)
            AND r.inserted_time is null)
          OR (b.build_end_time > '{2}' 
            AND b.build_end_time < '{3}')
    """
    if global_config.GAE_TESTING:
      query_str += 'limit 10'
    res = self.query(
        query_str.format(
            base_query_str,
            constants.application_id(),
            earliest_end_time_str,
            latest_end_time_str))
    res = _parse_bq_job_query(res)
    if res is None:
      return []

    build_infos = []
    for board, milestone, platform, build_config in res:
      board = _parse_board(build_config, board)
      build_infos.append(
          build_lib.BuildInfo(board, None, milestone, platform, build_config))

    return build_infos

  def get_relaxed_passed_builds(self, earliest_end_time, latest_end_time):
    """Get builds with successful "HWTest [sanity]" stages between a given span.

    Same as get_passed_builds, we run the query twice to ensure we fetched all
    builds from BQ.

    Args:
      earliest_end_time: a datetime.datetime object in UTC.
      latest_end_time: a datetime.datetime object in UTC.

    Returns:
      A list of build_lib.BuildInfo objects.
    """
    base_query_str = """
        SELECT
          JSON_EXTRACT_SCALAR(output.properties, '$.unibuild') as unibuild,
          s.name as stage_name,
          JSON_EXTRACT_SCALAR(output.properties, '$.board') as board,
          JSON_EXTRACT_SCALAR(output.properties, '$.milestone_version') as milestone,
          JSON_EXTRACT_SCALAR(output.properties, '$.platform_version') as platform,
          JSON_EXTRACT_SCALAR(output.properties, '$.cbb_config') as build_config,
          -- Time info
          c.end_time as build_end_time,
          CURRENT_TIMESTAMP() as inserted_time
        FROM
          `cr-buildbucket.chromeos.builds` as c,
          UNNEST(c.steps) AS s
        WHERE
          c.status != 'SUCCESS'
          AND s.name like 'SkylabHWTest%%'
          AND s.status = 'SUCCESS'
          AND JSON_EXTRACT_SCALAR(output.properties, '$.suite_scheduling') = 'True'
    """

    insert_relaxed_builds = """
        INSERT
          `google.com:{0}.builds.relaxed_builds`(
            unibuild,
            stage_name,
            board,
            milestone,
            platform,
            build_config,
            build_end_time,
            inserted_time
        ) {1}
        AND c.end_time > '{2}'
        AND c.end_time < '{3}'
    """
    earliest_end_time_str = earliest_end_time.strftime(
        time_converter.TIME_FORMAT)
    latest_end_time_str = latest_end_time.strftime(
        time_converter.TIME_FORMAT)

    if constants.application_id():
      logging.info('Insert the visible relaxed builds '
                   'between %s and %s to BQ.',
                   earliest_end_time_str, latest_end_time_str)
      self.query(
          insert_relaxed_builds.format(
              constants.application_id(),
              base_query_str,
              earliest_end_time_str,
              latest_end_time_str))

    logging.info('Getting relaxed passed builds finished between %s and %s',
                 earliest_end_time_str, latest_end_time_str)
    query_str = """
        WITH relaxed_builds AS
            ({0})
        SELECT
          b.unibuild,
          b.stage_name,
          b.board,
          b.milestone,
          b.platform,
          b.build_config,
        FROM
          relaxed_builds AS b
        LEFT JOIN
          `google.com:{1}.builds.relaxed_builds` AS r
          ON (
            r.board = b.board
            AND r.milestone = b.milestone
            AND r.build_config = b.build_config
            AND r.platform = b.platform
            AND r.build_end_time > TIMESTAMP_SUB(
                PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', '{2}'),
                INTERVAL 1 DAY)
            AND r.build_end_time < TIMESTAMP_SUB(
                PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', '{3}'),
                INTERVAL 1 DAY)
          )
        WHERE
          -- Check if any build was inserted to release builder
          -- in the past 24 hours.
          (b.build_end_time > TIMESTAMP_SUB(
              PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', '{2}'),
              INTERVAL 1 DAY)
            AND b.build_end_time < TIMESTAMP_SUB(
                PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%S', '{3}'),
                INTERVAL 1 DAY)
            AND r.inserted_time is null)
          OR (b.build_end_time > '{2}'
              AND b.build_end_time < '{3}')
    """
    if global_config.GAE_TESTING:
      query_str += 'limit 10'
    res = self.query(
        query_str.format(
            base_query_str,
            constants.application_id(),
            earliest_end_time_str,
            latest_end_time_str))
    res = _parse_bq_job_query(res)
    if res is None:
      return []

    build_infos = []
    for unibuild, stage_name, board, milestone, platform, build_config in res:
      board = _parse_board(build_config, board)
      if ast.literal_eval(unibuild):
        model = _parse_model(stage_name)
      else:
        model = None

      build_infos.append(
          build_lib.BuildInfo(board, model, milestone, platform, build_config))

    return build_infos


def _parse_bq_job_query(json_input):
  """Parse response from API bigquery.jobs.query.

  Args:
    json_input: a dict, representing jsons returned by query API.

  Returns:
    A 2D string matrix: [rows[columns]], or None if no result.
    E.g. Input:
    "rows": [
         {
          "f": [ # field
           {
            "v": 'foo1',
           },
           {
            "v": 'foo2',
           }
          ]
         }
         {
          "f": [ # field
           {
            "v": 'bar1',
           },
           {
            "v": 'bar2',
           }
          ]
         }
        ]
    => Output: [['foo1', 'foo2'], ['bar1', 'bar2']]
  """
  if 'rows' not in json_input:
    return None

  res = []
  for r in json_input['rows']:
    rc = []
    for c in r['f']:
      rc.append(c['v'])

    res.append(rc)

  return res


def _parse_model(build_stage_name):
  """Parse model name from the build stage name.

  It's only used for HWTest Sanity stage. An example build_stage_name will
  be 'HWTest [sanity] [whitetip]'.
  Args:
    build_stage_name: The stage name of a HWTest sanity stage, e.g.
      "HWTest [sanity] [whitetip]".

  Returns:
    A model name, e.g. "whitetip" or None.
  """
  if 'HWTest [sanity]' not in build_stage_name:
    return None

  try:
    model = build_stage_name.strip().split()[-1][1:-1]
    if not model:
      logging.warning('Cannot parse build stage name: %s', build_stage_name)
      return None

    return model
  except IndexError:
    logging.error('Cannot parse build stage name: %s', build_stage_name)
    return None


def _parse_board(build_config, board):
  """Parse board from build_config if needed.

  Board could be None for old release. See crbug.com/944981#c16.
  This function can be removed once all release are newer than R74.

  Args:
    build_config: A string build config, e.g. reef-release.
    board: A string board, e.g. reef.

  Returns:
    A string board if exist, or None.
  """
  if board is None:
    match = re.match(r'(.+)-release', build_config)
    if not match:
      logging.debug('Cannot parse board from %s', build_config)
      return None

    return match.groups()[0]

  return board
