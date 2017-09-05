# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for interacting with datastore."""
# pylint: disable=g-tzinfo-replace

import pytz

from google.appengine.ext import ndb


class LastExecutionRecord(ndb.Model):
  """Models a last_execute_record entry with keyword & exec_time."""

  # The keyword represents different types of events, e.g.
  # Key('LastExecutionRecord', 'nightly')
  event_type = ndb.StringProperty()

  # The last execute time for a given keyword.
  exec_time = ndb.DateTimeProperty()


class LastExecutionRecordStore(object):
  """Base class for reading google datastore."""

  def set_last_execute_time(self, event_type, exec_time):
    """Set the last execute time for the given keyword.

    Args:
      event_type: the keyword for saving last execute time.
      exec_time: The UTC timestamp for last execute time.

    Returns:
      The Key('LastExecutionRecord', event_type) to save the exec_time.
    """
    if exec_time.tzinfo is not None:
      exec_time = exec_time.replace(tzinfo=None)

    cur_record_key = ndb.Key(LastExecutionRecord, event_type)
    cur_record = cur_record_key.get()
    if cur_record is not None:
      cur_record.exec_time = exec_time
    else:
      cur_record = LastExecutionRecord(event_type=event_type,
                                       exec_time=exec_time)
      cur_record.key = cur_record_key

    return cur_record.put()

  def get_last_execute_time(self, event_type):
    """Get the last execute time for the given event_type.

    Args:
      event_type: the keyword to get its last execute time.

    Returns:
      last_exec_time: an offset-aware datetime object with timezone
        pytz.utc.
    """
    cur_record = ndb.Key(LastExecutionRecord, event_type).get()
    if cur_record is not None:
      return cur_record.exec_time.replace(tzinfo=pytz.utc)
    else:
      return None

  def del_last_execute_time(self, event_type):
    """Delete the last execute time for the given event_type.

    Args:
      event_type: the keyword to delete its last execute time.
    """
    cur_record_key = ndb.Key(LastExecutionRecord, event_type)
    if cur_record_key.get() is not None:
      cur_record_key.delete()

  def get_all(self):
    """Get the last execute time for all event_types in datastore.

    Returns:
      A list of LastExecutionRecord objects, whose exec_time is a
      offset-aware datetime object with timezone pytz.utc.
    """
    qry = LastExecutionRecord.query()
    for q in qry.iter():
      q.exec_time = q.exec_time.replace(tzinfo=pytz.utc)

    return [q for q in qry.iter()]

  def delete_all(self):
    """Delete the last execute time for all event_types in datastore."""
    for q in LastExecutionRecord.query().iter():
      q.key.delete()
