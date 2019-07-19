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

  def __init__(self, rest_client):
    """Initialize a REST client for connecting to Bigquery API."""
    self._rest_client = rest_client
    self._rest_client.create_service()

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


class CrOSSwarmingBigqueryClient(BigqueryRestClient):
  """REST client for chromeos-swarming Bigquery API."""

  def get_past_skylab_job_nums(self, hours):
    """Query the count of jobs kicked off to chromeos-swarming in past hours.

    Args:
      hours: An integer.

    Returns:
      An integer.
    """
    query_str = """
        SELECT
          COUNT(*)
        FROM
          `chromeos-swarming.swarming.task_requests` AS r
        WHERE
          'user:suite_scheduler' in UNNEST(r.tags) and
          create_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(),
          INTERVAL %d HOUR);
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

  def get_latest_passed_builds(self, build_config):
    """Get latest passed builds by build_config.

    Args:
      build_config: a string like '{board}-{build_type}', eg. link-release

    Returns:
      A build_lib.BuildInfo object representing the latest passed build.
    """
    query_str = """
        SELECT
          JSON_EXTRACT_SCALAR(output.properties, '$.board'),
          JSON_EXTRACT_SCALAR(output.properties, '$.milestone_version'),
          JSON_EXTRACT_SCALAR(output.properties, '$.platform_version')
        FROM
          `cr-buildbucket.chromeos.completed_builds_BETA`
        WHERE
          JSON_EXTRACT_SCALAR(output.properties, '$.cbb_config') = '%s' and
          status = 'SUCCESS' and
          JSON_EXTRACT_SCALAR(output.properties, '$.suite_scheduling') = 'True'
        ORDER BY
          end_time desc
        LIMIT 1
    """
    logging.info('Getting latest build for %s', build_config)
    res = self.query(query_str % build_config)
    res = _parse_bq_job_query(res)
    if res is None:
      return None

    return build_lib.BuildInfo(
        board=_parse_board(build_config, res[0][0]),
        model=None,
        milestone=res[0][1],
        platform=res[0][2],
        build_config=build_config)

  def get_latest_passed_builds_firmware(self, board):
    """Get latest passed firmware builds by board.

    Args:
      board: the board against which this task will run suite job.

    Returns:
      A build_lib.BuildInfo object representing the latest passed build.
    """
    query_str = """
        SELECT
          JSON_EXTRACT_SCALAR(output.properties, '$.board'),
          JSON_EXTRACT_SCALAR(output.properties, '$.milestone_version'),
          JSON_EXTRACT_SCALAR(output.properties, '$.platform_version')
        FROM
          `cr-buildbucket.chromeos.completed_builds_BETA`
        WHERE
          SPLIT(JSON_EXTRACT_SCALAR(output.properties,  '$.cbb_config'), '-')[OFFSET(0)] = 'firmware' and
          SPLIT(JSON_EXTRACT_SCALAR(output.properties,  '$.cbb_config'), '-')[OFFSET(1)] = '%s' and
          status = 'SUCCESS' and
          JSON_EXTRACT_SCALAR(output.properties, '$.suite_scheduling') = 'True'
        ORDER BY
          end_time desc
        LIMIT 1
    """
    logging.info('Getting latest build for %s-firmware', board)
    res = self.query(query_str % board)
    res = _parse_bq_job_query(res)
    if res is None:
      return None
    return build_lib.BuildInfo(
        board=board,
        model=None,
        milestone=res[0][1],
        platform=res[0][2],
        build_config='%s-firmware' % board)

  def get_passed_builds_since_date(self, since_date):
    """Get passed builds since a given date.

    Args:
      since_date: a datetime.datetime object in UTC.

    Returns:
      A list of build_lib.BuildInfo objects.
    """
    query_str = """
        SELECT
          JSON_EXTRACT_SCALAR(output.properties, '$.board'),
          JSON_EXTRACT_SCALAR(output.properties, '$.milestone_version'),
          JSON_EXTRACT_SCALAR(output.properties, '$.platform_version'),
          JSON_EXTRACT_SCALAR(output.properties, '$.cbb_config')
        FROM
          `cr-buildbucket.chromeos.completed_builds_BETA`
        WHERE
          end_time > '%s' and
          status = 'SUCCESS' and
          JSON_EXTRACT_SCALAR(output.properties, '$.suite_scheduling') = 'True'
    """
    if global_config.GAE_TESTING:
      since_date_str = '2019-05-19 20:00:00'
      query_str += 'limit 10'
    else:
      since_date_str = since_date.strftime(time_converter.TIME_FORMAT)

    logging.info('Getting passed builds since %s', since_date_str)
    res = self.query(query_str % since_date_str)
    res = _parse_bq_job_query(res)
    if res is None:
      return []

    build_infos = []
    for board, milestone, platform, build_config in res:
      board = _parse_board(build_config, board)
      build_infos.append(
          build_lib.BuildInfo(board, None, milestone, platform, build_config))

    return build_infos

  def get_relaxed_passed_builds_since_date(self, since_date):
    """Get builds with successful "HWTest [sanity]" stages since a given date.

    Args:
      since_date: a datetime.datetime object in UTC.

    Returns:
      A list of build_lib.BuildInfo objects.
    """
    query_str = """
        SELECT
          JSON_EXTRACT_SCALAR(output.properties, '$.unibuild'),
          s.name,
          JSON_EXTRACT_SCALAR(output.properties, '$.board'),
          JSON_EXTRACT_SCALAR(output.properties, '$.milestone_version'),
          JSON_EXTRACT_SCALAR(output.properties, '$.platform_version'),
          JSON_EXTRACT_SCALAR(output.properties, '$.cbb_config')
        FROM
          `cr-buildbucket.chromeos.completed_builds_BETA` as c,
          UNNEST(c.steps) AS s
        WHERE
          c.end_time > '%s' and
          c.status != 'SUCCESS' and
          s.name like '%%HWTest [sanity]%%' and
          s.status = 'SUCCESS' and
          JSON_EXTRACT_SCALAR(output.properties, '$.suite_scheduling') = 'True'
    """
    if global_config.GAE_TESTING:
      since_date_str = '2019-05-19 20:00:00'
      query_str += 'limit 10'
    else:
      since_date_str = since_date.strftime(time_converter.TIME_FORMAT)

    logging.info('Getting passed builds since %s', since_date_str)
    res = self.query(query_str % since_date_str)
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
