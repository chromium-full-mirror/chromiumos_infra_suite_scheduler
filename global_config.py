# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for managing runtime configs for suite scheduler."""

import constants


def is_in_staging():
  """Check whether this script is running on staging instance or not.

  Returns:
    A boolean indicating the script is running on staging instance
    suite-scheduler-staging.googleplex.com or not.
  """
  return (constants.environment() == constants.RunningEnv.ENV_PROD and
          constants.application_id() == constants.AppID.STAGING_APP)


# Explicitly specify GAE_TESTING here for the following reasons:
# 1) to make it obvious that it's testing on GAE instance.
# 2) in case there's other requirements more than is_in_staging for detecting
#    whether it's testing on GAE instance.
GAE_TESTING = is_in_staging()
