# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for interacting with google APIs."""

import apiclient
import httplib2
import os

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
        self._running_env = constants.environment()
        self._scopes = scopes
        self._service_name = service_name
        self._service_version = service_version

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
                self._service_name, self._service_version,
                http=http_auth)
        else:
            self._service = apiclient.discovery.build(
                self._service_name, self._service_version, http=http_auth,
                discoveryServiceUrl=discovery_url)

    def _init_credentials(self):
        """Initialize the credentials for a google API."""
        if (self._running_env == constants.RunningEnv.ENV_STANDALONE or
            self._running_env == constants.RunningEnv.ENV_DEVELOPMENT_SERVER):
            # Running locally
            service_credentials = service_account.ServiceAccountCredentials
            self._credentials = service_credentials.from_json_keyfile_name(
                file_getter.LOCAL_CLIENT_SECRETS_FILE, self._scopes)
        else:
            # Running in app-engine production
            self._credentials = appengine.AppAssertionCredentials(self._scopes)


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

    def ReadObject(self, input_bucket, input_object):
        """Read the contents of input_object in input_bucket.

        Args:
            input_bucket: the bucket for fetching.
            input_object: the object for checking the contents.

        Returns:
            the stripped string contents of the input object.

        Raises:
            apiclient.errors.HttpError
        """
        req = self._rest_client.service.objects().get_media(
            bucket=input_bucket,
            object=input_object)
        return req.execute()


class CalendarRestClient(object):
    """Class of REST client for google calendar API."""

    def __init__(self, rest_client):
        """Initialize a REST client for connecting to Google calendar API."""
        self._rest_client = rest_client
        self._rest_client.create_service()

    def AddEvent(self, calendar_id, input_event):
        """Add events of a given calendar.

        Args:
            calendarId: the ID of the given calendar.
            input_event: the event to be added.
            kwargs: the parameters for adding events of the calendar.
        """
        self._rest_client.service.events().insert(
            calendarId=calendar_id,
            body=input_event).execute()


class SwarmingRestClient(object):
    """REST client for swarming proxy API."""

    DISCOVERY_URL_PATTERN = '%s/discovery/v1/apis/%s/%s/rest'

    def __init__(self, rest_client, service_url):
        self._rest_client = rest_client
        discovery_url = self.DISCOVERY_URL_PATTERN % (
            service_url, service_name, service_version)
        self._rest_client.create_service(discovery_url=discovery_url)

    def create_task(self, request):
        """Create new task.

        Args:
            request: a json-compatible dict expected by swarming server.
                See _to_raw_request's output in swarming_lib.py for details.
        """
        return self._rest_client.service.tasks().new(
            fields='request,task_id', body=request).execute()

    def request_task(self, task_id):
        """Get task details by a given task_id.

        Args:
            task_id: A string, represents task id.

        Returns:
            A json dict returned by API task.request.
        """
        return self._rest_client.service.task().request(
            task_id=task_id).execute()
