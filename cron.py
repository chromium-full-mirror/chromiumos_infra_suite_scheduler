# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for cron jobs kicked off by suite scheduler."""
# pylint: disable=g-bad-import-order

import logging
import webapp2

import constants
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

_CALENDAR_TIMEZONE = 'America/Los_Angeles'


class TriggerEvent(webapp2.RequestHandler):
  """Trigger events regularly to schedule tasks for suite_scheduler."""

  def get(self):
    # Don't kick off cron job in staging instance. This cron job can be
    # kicked off On local development env or prod instance.
    if global_config.is_in_staging():
      return

    start_time = time_converter.pst_now()
    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()
    end_time = time_converter.pst_now()

    calendar_client = rest_client.CalendarRestClient(
        rest_client.BaseRestClient(
            constants.RestClient.CALENDAR_CLIENT.scopes,
            constants.RestClient.CALENDAR_CLIENT.service_name,
            constants.RestClient.CALENDAR_CLIENT.service_version))

    for keyword, results in suite_trigger.event_results.iteritems():
      # No finished tasks for the given keyword
      if not results:
        continue

      event = {}
      event['summary'] = '%s Suite Tasks - Scheduled' % keyword
      description = '%d scheduled tasks: \n' % len(results)
      for task_name in results:
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
        calendar_client.add_event(_PROD_CALENDAR_ID_MAPPING[keyword], event)
      else:
        logging.info(event)


class ExecuteTask(webapp2.RequestHandler):
  """Run scheduled tasks regularly for suite_scheduler."""

  def get(self):
    if global_config.is_in_staging():
      return

    task_processor = task_executor.TaskProcessor(task_executor.SUITES_QUEUE)
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

    suite_trigger = trigger_receiver.TriggerReceiver()
    suite_trigger.cron()

    task_processor = task_executor.TaskProcessor(task_executor.SUITES_QUEUE)
    task_processor.batch_execute()
    # In testing, after one round of batch_execute() to execute all tasks,
    # the suite queue will be purged.
    task_processor.purge()


app = webapp2.WSGIApplication([
    ('/cron/trigger_event', TriggerEvent),
    ('/cron/execute_task', ExecuteTask),
    ('/cron/test_push', TestPush),
], debug=True)
