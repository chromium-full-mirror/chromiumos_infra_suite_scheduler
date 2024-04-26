#!/usr/bin/env python2
# Copyright 2024 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Module for helper function unittests."""

import json
import request_helper
import unittest
import sys

# Manually bring in this library.
sys.path.append('infra_libs')

from chromite.api.gen.test_platform import request_pb2 as ctp_request
from chromite.api.gen.chromiumos.test.api import ctp2_pb2 as ctpv2_request

class MockFilterGenerationTestCase(unittest.TestCase):

    def _build_filter(self):
        karbon_filters = [
            {
                "containerInfo": {
                    "container": {
                        "repository": {
                            "hostname": "hostname",
                            "project": "project"
                        },
                        "name": "name",
                        "digest": "sha256:fake",
                        "tags": ["tag1", "tag2"]
                    },
                    "binaryName": "test-udf",
                    "binaryArgs": [
                        "-example", "arg"
                    ]
                }
            }
        ]
        return json.dumps(karbon_filters)

    def testFilterGenerationForV1Request(self):
        request = ctp_request.Request()
        params = request.params
        karbon_filters_str = self._build_filter()
        karbon_filters = json.loads(karbon_filters_str)
        request_helper.form_ctpv2_filters(params.user_defined_filters, karbon_filters)

        self.assertEqual(len(params.user_defined_filters), 1)
        c_info = params.user_defined_filters[0].container_info
        self.assertEqual(c_info.binary_name, "test-udf")
        self.assertEqual(len(c_info.binary_args), 2)
        self.assertEqual(c_info.binary_args[0], "-example")
        self.assertEqual(c_info.binary_args[1], "arg")
        cont = c_info.container
        self.assertEqual(cont.repository.hostname, "hostname")
        self.assertEqual(cont.repository.project, "project")
        self.assertEqual(cont.name, "name")
        self.assertEqual(cont.digest, "sha256:fake")
        self.assertEqual(len(cont.tags), 2)
        self.assertEqual(cont.tags[0], "tag1")
        self.assertEqual(cont.tags[1], "tag2")
