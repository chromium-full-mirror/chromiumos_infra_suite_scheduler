# Copyright 2023 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for a retry decorator."""

import logging
import time


def retry(max_retries, first_retry_delay_in_seconds=1, backoff=2):
  """Retry decorator function retries on exception.

  max_retries: Max number of retries before raise exception.
  first_retry_delay_in_seconds: Number of seconds before first retry.
  backoff: Factor of exponential backoff for each retry
  """
  if max_retries < 0:
    raise ValueError("max_tries must be 0 or greater")

  if first_retry_delay_in_seconds <= 0:
    raise ValueError("first_retry_delay_in_seconds must be greater than 0")

  if backoff <= 1:
    raise ValueError("backoff must be greater than 1")

  def deco_retry(func):
    def wrapper(*args, **kwargs):
      delay = first_retry_delay_in_seconds
      for cnt in range(max_retries + 1):
        try:
          return func(*args, **kwargs)
        except Exception as ex:
          if cnt < max_retries:
            logging.warning(
                "Retrying %s() in %ds due to exception: %s" % (
                    func.__name__, delay, str(ex)), exc_info=True)
            delay = backoff * delay
            time.sleep(delay)
          else:
            logging.error(
                "Hit retry limit of %d for %s()" % (
                    max_retries, func.__name__))
            raise

    return wrapper

  return deco_retry
