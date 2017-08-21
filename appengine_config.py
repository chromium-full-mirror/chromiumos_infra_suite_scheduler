# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for current GAE project's configs."""

import os
from google.appengine.ext import vendor

# Add any third-party libraries install in the "lib" folder.
third_party_lib_path = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), 'lib')
if os.path.exists(third_party_lib_path):
  vendor.add(third_party_lib_path)
