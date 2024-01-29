# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module used to wrap the logging commands incase of phantom errors."""

import logging


def getLogger(level):
  try:
    logging.getLogger().setLevel(level)
  except:
    try:
      logging.getLogger().setLevel(level)
    except:
      pass

def info(msg, *args, **kwargs):
  try:
    logging.info(msg, *args, **kwargs)
  except:
    try:
      logging.info(msg, *args, **kwargs)
    except:
      pass


def warning(msg, *args, **kwargs):
  try:
    logging.warning(msg, *args, **kwargs)
  except:
    try:
      logging.warning(msg, *args, **kwargs)
    except:
      pass

def debug(msg, *args, **kwargs):
  try:
    logging.debug(msg, *args, **kwargs)
  except:
    try:
      logging.debug(msg, *args, **kwargs)
    except:
      pass

def error(msg, *args, **kwargs):
  try:
    logging.error(msg, *args, **kwargs)
  except:
    try:
      logging.error(msg, *args, **kwargs)
    except:
      pass

def exception(msg, *args, **kwargs):
  try:
    logging.exception(msg, *args, **kwargs)
  except:
    try:
      logging.exception(msg, *args, **kwargs)
    except:
      pass
