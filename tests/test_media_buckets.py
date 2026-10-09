# SPDX-License-Identifier: AGPL-3.0-only

import unittest

from choice.media import edge_for_viewport, snap_edge


class MediaBucketTests(unittest.TestCase):
    def test_snap_edge_buckets(self):
        self.assertEqual(snap_edge(500), 640)
        self.assertEqual(snap_edge(700), 960)
        self.assertEqual(snap_edge(1100), 1280)
        self.assertEqual(snap_edge(2000), 1600)

    def test_viewport_dpr(self):
        self.assertEqual(edge_for_viewport(400, 2), 960)
