# SPDX-License-Identifier: AGPL-3.0-only

import json
import tempfile
import unittest
from pathlib import Path

from choice.people import load_roster, save_roster, Person


class RosterOwnerTests(unittest.TestCase):
    def test_owner_defaults_to_first_person(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / ".choice" / "users.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "users": [
                            {"id": "alice", "name": "Alice", "decks": "*"},
                            {"id": "bob", "name": "Bob", "decks": ["d1"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            roster = load_roster(root)
            self.assertTrue(roster.enabled)
            self.assertEqual(roster.owner_id, "alice")

    def test_explicit_owner_preserved_on_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / ".choice" / "users.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "owner": "bob",
                        "users": [
                            {"id": "alice", "name": "Alice", "decks": "*"},
                            {"id": "bob", "name": "Bob", "decks": "*"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            save_roster(root, [Person("alice", "Alice", None)])
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data.get("owner"), "bob")


if __name__ == "__main__":
    unittest.main()
