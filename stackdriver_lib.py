# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for stackdriver related functions."""

import os


# The format of loggings.
LOGGING_FORMAT = ('%(time)s %(levelname)-5.5s|%(module)'
                  '18.18s:%(lineno)4.4s| %(message)s')


def form_logging_client_request(project_id, utc_start_time, utc_end_time,
                                resource_name, order_by='timestamp asc'):
  """Form a request that can be used by stackdriver logger API.

  Args:
    project_id: the GAE project id.
    utc_start_time: A string representing UTC time, in format of
      converter.STACKDRIVER_TIME_FORMAT.
    utc_end_time: A string representing UTC time, in format of
      converter.STACKDRIVER_TIME_FORMAT.
    resource_name: the resouce of the logs to fetch.
    order_by: the order of the logs. By default it's asc in time.

  Returns:
    A dict representing formalized request.
  """
  request = {}
  request['projectIds'] = [project_id]
  request['orderBy'] = order_by
  request['filter'] = (
      'protoPayload.resource = "%s" AND '
      'protoPayload.startTime > "%s" AND '
      'protoPayload.endTime < "%s"' % (
          resource_name, utc_start_time, utc_end_time))
  return request


def parse_logging_client_response(logs):
  """Parse json object returned by stackDriver client.

  Args:
    logs: A json object includes all logs.

  Returns:
    A string includes all lines of logs, where each line is split by
    a newline.
  """
  response = ''
  if 'entries' not in logs:
    return response

  for entry in logs['entries']:
    if 'line' not in entry['protoPayload']:
      continue

    for line in entry['protoPayload']['line']:
      response += _form_logging_line(line) + '\n'

  return response


def _form_logging_line(line):
  """Form each line of logs with specified format.

  Args:
    line: A json object including all required information of a logging line.

  Returns:
    A string of logs formatted by LOGGING_FORMAT.
  """
  module, lineno = _parse_file_info(line)
  formatted_line = LOGGING_FORMAT % {'time': line['time'],
                                     'levelname': line['severity'],
                                     'module': module,
                                     'lineno': lineno,
                                     'message': line['logMessage']}
  return formatted_line


def _parse_file_info(line):
  """Parse the file information from line object.

  Args:
    line: A json object including file location and line number.

  Returns:
    A tuple of file location & line number in file.
  """
  try:
    source = line['sourceLocation']
    return os.path.basename(source['file']), source['line']
  except KeyError:
    return '', ''
