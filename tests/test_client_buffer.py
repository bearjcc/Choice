# SPDX-License-Identifier: AGPL-3.0-only

import unittest

from choice.client_buffer import merge_held_pile, parse_held


class ClientBufferTests(unittest.TestCase):
    def test_merge_held_keeps_client_order_at_front(self):
        pile = ["z", "a", "b", "c"]
        held = ["a", "b"]
        self.assertEqual(merge_held_pile(pile, held), ["a", "b", "z", "c"])

    def test_merge_skips_vanished_held(self):
        pile = ["x", "y"]
        held = ["gone", "x"]
        self.assertEqual(merge_held_pile(pile, held), ["x", "y"])

    def test_parse_held_respects_limit(self):
        raw = ",".join(f"i{n}" for n in range(50))
        self.assertEqual(len(parse_held(raw, limit=10)), 10)


if __name__ == "__main__":
    unittest.main()
