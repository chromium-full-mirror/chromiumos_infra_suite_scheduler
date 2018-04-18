# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for cron jobs kicked off by suite scheduler."""
# pylint: disable=g-bad-import-order

import datetime
import logging
import webapp2

import constants
import config_reader
import file_getter
import global_config
import rest_client
import task_executor
import time_converter
import trigger_receiver


_PROD_CALENDAR_ID_MAPPING = {
    'new_build': constants.CalendarID.PROD_NEW_BUILD,
    'nightly': constants.CalendarID.PROD_NIGHTLY,
    'weekly': constants.CalendarID.PROD_WEEKLY,
}

_STAGING_CALENDAR_ID_MAPPING = {
    'new_build': constants.CalendarID.STAGING_NEW_BUILD,
    'nightly': constants.CalendarID.STAGING_NIGHTLY,
    'weekly': constants.CalendarID.STAGING_WEEKLY,
}

# Timezone used in calendar, indicating PST.
_CALENDAR_TIMEZONE = 'America/Los_Angeles'

# Log time extension minutes.
_LOG_TIME_ADDON_MIN = 1

# The format of url of loggings.
_LOGGING_URL_FORMAT = 'http://%s/logger?start_time=%s&end_time=%s&resource=%s'


class TriggerEvent(webapp2.RequestHandler):
  """Trigger events regularly to schedule tasks for suite_scheduler."""

  def get(self):
    # Don't kick off cron job in staging instance. This cron job can be
    # kicked off On local development env or prod instance.
    if global_config.is_in_staging():
      return

    start_time = time_converter.pst_now()
    utc_start_time = time_converter.utc_now()
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()
    end_time = time_converter.pst_now()
    utc_end_time = time_converter.utc_now()
    calendar_client = rest_client.CalendarRestClient(
        rest_client.BaseRestClient(
            constants.RestClient.CALENDAR_CLIENT.scopes,
            constants.RestClient.CALENDAR_CLIENT.service_name,
            constants.RestClient.CALENDAR_CLIENT.service_version))
    str_start_time, str_end_time = _adjust_log_time(
        utc_start_time, utc_end_time)
    log_url = _LOGGING_URL_FORMAT % (
        constants.server_name(), str_start_time, str_end_time,
        '/cron/trigger_event')
    logging.info('URL for logs of current round of event trigger: %s', log_url)

    for keyword, results in suite_trigger.event_results.iteritems():
      # No finished tasks for the given keyword
      if not results:
        continue

      _add_to_calendar(keyword, results, log_url, start_time, end_time,
                       calendar_client, _PROD_CALENDAR_ID_MAPPING[keyword])


class ExecuteTask(webapp2.RequestHandler):
  """Run scheduled tasks regularly for suite_scheduler."""

  def get(self):
    if global_config.is_in_staging():
      return

    lab_config = config_reader.LabConfig(config_reader.ConfigReader(
        file_getter.LAB_CONFIG_FILE))
    afe_server = lab_config.get_dedicated_afe()
    task_processor = task_executor.TaskProcessor(task_executor.SUITES_QUEUE,
                                                 afe_server)
    task_processor.batch_execute()


class TestPush(webapp2.RequestHandler):
  """Test push for suite_scheduler on staging instance."""

  def get(self):
    if not global_config.is_in_staging():
      return

    # Test Cron jobs
    # 1) No tasks will be filtered by nightly/weekly constraints.
    # 2) Randomly select builds in |get_cros_builds_since_date_from_db|.
    # 3) Every task will be kicked off with dummy swarming run |dummy_run|.
    start_time = time_converter.pst_now()
    utc_start_time = time_converter.utc_now()
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()
    end_time = time_converter.pst_now()
    utc_end_time = time_converter.utc_now()
    calendar_client = rest_client.CalendarRestClient(
        rest_client.BaseRestClient(
            constants.RestClient.CALENDAR_CLIENT.scopes,
            constants.RestClient.CALENDAR_CLIENT.service_name,
            constants.RestClient.CALENDAR_CLIENT.service_version))
    str_start_time, str_end_time = _adjust_log_time(
        utc_start_time, utc_end_time)
    log_url = _LOGGING_URL_FORMAT % (
        constants.server_name(), str_start_time, str_end_time,
        '/cron/test_push')
    logging.info('URL for logs of current round of test_push: %s', log_url)

    task_processor = task_executor.TaskProcessor(task_executor.SUITES_QUEUE)
    task_processor.batch_execute()
    # In testing, after one round of batch_execute() to execute all tasks,
    # the suite queue will be purged.
    task_processor.purge()

    for keyword, results in suite_trigger.event_results.iteritems():
      # No finished tasks for the given keyword
      if not results:
        continue

      _add_to_calendar(keyword, results, log_url, start_time, end_time,
                       calendar_client, _STAGING_CALENDAR_ID_MAPPING[keyword])


def _adjust_log_time(utc_start_time, utc_end_time):
  """Adjust the start and end time for logging.

  In order to ensure that logs can be fetched by a proper time window,
  slightly enlarge the log time window by extending 2 * _LOG_TIME_ADDON_MIN.

  Args:
    utc_start_time: a datetime.datetime object in UTC indicating when the logs
      are started.
    utc_end_time: a datetime.datetime object in UTC indicating when the logs
      are ended.

  Returns:
    A tuple of two strings indicating start_time and end_time in format
    time_converter.STACKDRIVER_TIME_FORMAT.
  """
  real_start_time = utc_start_time - datetime.timedelta(
      minutes=_LOG_TIME_ADDON_MIN)
  real_end_time = utc_end_time + datetime.timedelta(
      minutes=_LOG_TIME_ADDON_MIN)
  return (
      real_start_time.strftime(time_converter.STACKDRIVER_TIME_FORMAT),
      real_end_time.strftime(time_converter.STACKDRIVER_TIME_FORMAT))


def _add_to_calendar(keyword, task_results, log_url, start_time, end_time,
                     calendar_client, calendar_id):
  """Formalize task results and add them to calendar.

  Args:
    keyword: the suite scheduler event type.
    task_results: the finished tasks, represented by a list.
    log_url: a string url for fetching the logs.
    start_time: a datetime.datetime object in PST.
    end_time: a datetime.datetime object in PST.
    calendar_client: a rest_client.CalendarRestClient object.
    calendar_id: a string calendar ID.
  """
  event = {}
  event['summary'] = '%s Suite Tasks - Scheduled' % keyword
  description = '<a href=%s>Running Logs</a>\n%d scheduled tasks: \n' % (
      log_url, len(task_results))
  for task_name in task_results:
    description += task_name + '\n'
  event['description'] = description
  # The start time is exactly when the cron job is triggered, i.e. when
  # all tasks of this event are pushed into the task queue. It's not
  # when the tasks are 'really' kicked off in lab because there will be
  # some time delay since task queue will schedule tasks batch by batch.
  # However, the end time is not exactly when the cron job is finished,
  # since this cron job's runtime is very short, but the calendar won't
  # show any item that's shorter than 30 minutes. So no matter what
  # endtime we set here, it will show a half-an-hour event.
  event['start'] = {
      'dateTime': start_time.strftime(time_converter.CALENDAR_TIME_FORMAT),
      'timeZone': _CALENDAR_TIMEZONE,
  }
  event['end'] = {
      'dateTime': end_time.strftime(time_converter.CALENDAR_TIME_FORMAT),
      'timeZone': _CALENDAR_TIMEZONE,
  }
  if constants.environment() == constants.RunningEnv.ENV_PROD:
    calendar_client.add_event(calendar_id, event)
  else:
    logging.info(event)


app = webapp2.WSGIApplication([
    ('/cron/trigger_event', TriggerEvent),
    ('/cron/execute_task', ExecuteTask),
    ('/cron/test_push', TestPush),
], debug=True)
