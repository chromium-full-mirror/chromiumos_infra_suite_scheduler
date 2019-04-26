# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for interacting with google APIs."""
# pylint: disable=g-bad-import-order
# pylint: disable=g-bad-exception-name

import httplib2

import apiclient
import constants
import file_getter

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

  def __init__(self, rest_client):
    """Initialize a REST client for connecting to Bigquery API."""
    self._rest_client = rest_client
    self._rest_client.create_service()

  def get_past_skylab_job_nums(self, hours):
    """Query skylab job numbers scheduled in past hours.

    Args:
      hours: An integer.

    Returns:
      A json dict returned by API bigquery.jobs.query, e.g.
      # {...,
      #  "rows": [
      #     {
      #      "f": [ # field
      #       {
      #        "v": # value
      #       }
      #      ]
      #     }
      #   ]
      # }
    """
    query_data = {
        'query': ('SELECT COUNT(*) FROM swarming.task_requests AS r '
                  'WHERE \'user:suite_scheduler\' in UNNEST(r.tags) and '
                  'create_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), '
                  'INTERVAL %d HOUR);') % hours,
        'useLegacySql': False
    }
    return self._rest_client.service.jobs().query(
        projectId='chromeos-swarming',
        body=query_data).execute()
