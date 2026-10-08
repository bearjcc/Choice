# SPDX-License-Identifier: AGPL-3.0-only
"""Choice keeps its promises: a swipe is a line in the log, and trash is a move."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from choice.act import decide, progress, undo
from choice.cli import _print_tally
from choice.flow import arrange
from choice.httpd import ChoiceSite
from choice.load import DeckProblem, resolve
from choice.people import Person, assignment_warnings, load_roster, parse_users

ROOT = Path(__file__).resolve().parents[1]


class ChoiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_examples_are_a_library(self):
        opened = resolve(ROOT / "examples")
        self.assertFalse(opened.direct)
        self.assertEqual(
            sorted(deck.id for deck in opened.decks),
            ["immich", "knockout", "photos", "pigs", "round-robin", "true-false", "which-one", "yes-no"],
        )
        immich = next(deck for deck in opened.decks if deck.id == "immich")
        photos, photo_warnings = immich.load_items()
        self.assertEqual(photo_warnings, [])
        self.assertIsNone(immich.hook)
        self.assertEqual([item.kind for item in photos], ["image", "image"])
        self.assertEqual([item.id for item in photos], ["asset-id-1", "asset-id-2"])
        which = next(deck for deck in opened.decks if deck.id == "which-one")
        items, warnings = which.load_items()
        self.assertEqual(warnings, [])
        self.assertEqual(items[0].kind, "pair")
        self.assertEqual(items[0].title, "Shorter reply")
        self.assertEqual([side.label for side in items[0].sides], ["A", "B"])
        self.assertEqual(items[0].sides[0].body, "Yes.")
        self.assertTrue(items[0].sides[1].body.startswith("Yes, I think so"))
        self.assertEqual(items[0].reveal[0][0], "real")
        self.assertEqual(items[0].chips, [])
        quiz = next(deck for deck in opened.decks if deck.id == "true-false")
        self.assertEqual(quiz.score_field, "answer")
        self.assertTrue(quiz.blind)
        questions, quiz_warnings = quiz.load_items()
        self.assertEqual(quiz_warnings, [])
        self.assertEqual(len(questions), 8)
        self.assertEqual(questions[0].chips, [])
        robin = next(deck for deck in opened.decks if deck.id == "round-robin")
        self.assertEqual(robin.contest_kind, "robin")
        names, _robin_warnings = robin.load_items()
        robin_flow = arrange(robin, names, {})
        self.assertEqual(len(robin_flow.items), 10)
        pairs = {tuple(sorted((item.fields["a"], item.fields["b"]))) for item in robin_flow.items}
        self.assertEqual(len(pairs), 10)
        bracket = next(deck for deck in opened.decks if deck.id == "knockout")
        shelters, _bracket_warnings = bracket.load_items()
        bracket_flow = arrange(bracket, shelters, {})
        self.assertEqual([item.title for item in bracket_flow.items], ["Quarter-final"] * 4)
        self.assertEqual(
            [(item.sides[0].body, item.sides[1].body) for item in bracket_flow.items],
            [
                ("Cairn Hut", "Deer Leap"),
                ("East Wall", "Fox Bend"),
                ("Grey Pool", "Hare Gate"),
                ("Ivy Step", "Juniper"),
            ],
        )
        pigs = next(deck for deck in opened.decks if deck.id == "pigs")
        scenes, pig_warnings = pigs.load_items()
        self.assertEqual(pig_warnings, [])
        opening = arrange(pigs, scenes, {})
        self.assertEqual([item.id for item in opening.items], ["road"])
        self.assertEqual(opening.items[0].offers, {"left": "Stay together", "right": "Split the tools"})
        self.assertEqual(opening.count_label, "Scene 1")
        self.assertFalse(opening.meter)

    def test_immich_hook_stays_quiet_until_a_bin_or_favourite(self):
        script = ROOT / "examples" / "immich" / "hook.py"
        env = os.environ.copy()
        env.pop("IMMICH_URL", None)
        env.pop("IMMICH_API_KEY", None)
        kept = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps({"action": "decide", "item": "asset-id-1", "value": "keep"}).encode(),
            capture_output=True,
            cwd=self.tmp,
            env=env,
        )
        self.assertEqual(kept.returncode, 0)
        binned = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps({
                "action": "decide",
                "item": "asset-id-1",
                "value": "bin",
                "decision_id": "d1",
            }).encode(),
            capture_output=True,
            cwd=self.tmp,
            env=env,
        )
        self.assertEqual(binned.returncode, 1)
        self.assertIn(b"IMMICH_URL", binned.stderr)
        self.assertFalse((self.tmp / ".choice" / "immich.jsonl").exists())

    def test_pair_images_serve_each_side(self):
        (self.tmp / "a.png").write_bytes(b"aaa-png")
        (self.tmp / "b.png").write_bytes(b"bbb-png")
        (self.tmp / "items.jsonl").write_text(
            '{"id":"1","before":"a.png","after":"b.png","note":"Portraits"}\n{"id":"2","before":"","after":"b.png"}\n',
            encoding="utf-8",
        )
        (self.tmp / "deck.json").write_text(
            json.dumps({
                "title": "Pair",
                "source": {"type": "jsonl", "path": "items.jsonl"},
                "show": {
                    "title": "{{note}}",
                    "pair": {
                        "a": {"image": "before", "label": "Earlier"},
                        "b": {"image": "after", "body": "{{note}}"},
                    },
                },
                "directions": {
                    "left": {"label": "Before", "value": "before"},
                    "right": {"label": "After", "value": "after"},
                },
            }),
            encoding="utf-8",
        )
        deck = resolve(self.tmp).decks[0]
        items, warnings = deck.load_items()
        self.assertEqual(items[0].kind, "pair")
        self.assertEqual(items[0].sides[0].label, "Earlier")
        self.assertEqual(items[0].sides[1].label, "After")
        self.assertEqual(items[0].sides[1].body, "Portraits")
        self.assertTrue(str(items[0].sides[0].path).endswith("a.png"))
        self.assertTrue(any("pair a:" in line and "empty" in line for line in warnings))
        pub = items[0].public(None)
        self.assertTrue(pub["sides"][0]["media"])
        self.assertNotIn("path", pub["sides"][0])

        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            index = self._get(port, "/api/index")
            deck_id = index["decks"][0]["id"]
            left = self._open(port, "/api/decks/%s/media?item=1&side=a" % deck_id)
            right = self._open(port, "/api/decks/%s/media?item=1&side=b" % deck_id)
            bare = self._open(port, "/api/decks/%s/media?item=1" % deck_id)
            other = self._open(port, "/api/decks/%s/media?item=1&side=nope" % deck_id)
            self.assertEqual(left.status, 200)
            self.assertEqual(left.body, "aaa-png")
            self.assertEqual(right.body, "bbb-png")
            self.assertEqual(bare.status, 404)
            self.assertEqual(other.status, 404)
        finally:
            server.shutdown()
            server.server_close()

    def test_pair_needs_both_sides(self):
        (self.tmp / "items.jsonl").write_text('{"id":"1","A":"one"}\n', encoding="utf-8")
        (self.tmp / "deck.json").write_text(
            json.dumps({
                "source": {"type": "jsonl", "path": "items.jsonl"},
                "show": {"pair": {"a": "{{A}}"}},
            }),
            encoding="utf-8",
        )
        with self.assertRaises(DeckProblem):
            resolve(self.tmp).decks[0].load_items()

    def test_point_at_a_jsonl_file(self):
        path = self.tmp / "quiz.jsonl"
        path.write_text('{"id":"a","q":"Ready?"}\n', encoding="utf-8")
        opened = resolve(path)
        self.assertTrue(opened.direct)
        deck = opened.decks[0]
        self.assertEqual(deck.id, "quiz-jsonl")
        items, _warnings = deck.load_items()
        self.assertEqual(items[0].title, "Ready?")

    def test_folder_of_photos_results_mode_keeps_files(self):
        (self.tmp / "one.png").write_bytes(b"png")
        (self.tmp / "two.png").write_bytes(b"png")
        deck = resolve(self.tmp).decks[0]
        self.assertEqual(deck.directions["left"].does, "label")
        result = decide(deck, "one.png", "left", None)
        self.assertTrue(result["ok"], result)
        self.assertTrue((self.tmp / "one.png").is_file())
        snap = progress(deck, pending=True)
        self.assertEqual(snap["left"], 1)

    def test_folder_sort_moves_and_undoes(self):
        (self.tmp / "deck.json").write_text(
            json.dumps(
                {
                    "source": {
                        "type": "images",
                        "path": ".",
                        "output": "sort",
                        "sort": {"left": ".choice/trash"},
                    },
                    "directions": {
                        "right": {"label": "Keep", "value": "keep"},
                        "left": {"label": "Trash", "value": "trash"},
                        "down": {"label": "Skip", "value": "skip", "later": True},
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.tmp / "one.png").write_bytes(b"png")
        deck = resolve(self.tmp).decks[0]
        self.assertEqual(deck.directions["left"].does, "move")
        result = decide(deck, "one.png", "left", None)
        self.assertTrue(result["ok"], result)
        self.assertFalse((self.tmp / "one.png").exists())
        self.assertTrue((self.tmp / ".choice" / "trash" / "one.png").is_file())
        undone = undo(deck)
        self.assertTrue(undone["ok"], undone)
        self.assertTrue((self.tmp / "one.png").is_file())

    def test_skip_stays_in_the_pile_and_a_later_swipe_wins(self):
        self._write_yes_no([{"id": "1", "q": "Keep it?"}])
        deck = resolve(self.tmp).decks[0]
        decide(deck, "1", "down", None)
        snap = progress(deck, pending=True)
        self.assertEqual(snap["left"], 1)
        self.assertEqual(snap["items"][0]["id"], "1")
        decide(deck, "1", "right", "sure")
        decide(deck, "1", "left", None)
        undo(deck)
        snap = progress(deck, pending=False)
        self.assertEqual(snap["items"][0]["choice"], "yes")
        self.assertEqual(snap["decided"], 1)

    def test_bad_into_is_refused(self):
        (self.tmp / "deck.json").write_text(
            json.dumps({"directions": {"left": {"label": "Out", "does": "move", "into": "../out"}}}),
            encoding="utf-8",
        )
        with self.assertRaises(DeckProblem):
            resolve(self.tmp)

    def test_outside_file_is_not_moved(self):
        src = self.tmp / "src"
        src.mkdir()
        (src / "note.txt").write_text("hello", encoding="utf-8")
        deck_dir = self.tmp / "deck"
        deck_dir.mkdir()
        (deck_dir / "deck.json").write_text(
            json.dumps({
                "source": {"type": "files", "path": str(src)},
                "directions": {"left": {"label": "Trash", "does": "move", "into": ".choice/trash"}},
            }),
            encoding="utf-8",
        )
        deck = resolve(deck_dir).decks[0]
        result = decide(deck, "note.txt", "left", None)
        self.assertFalse(result["ok"])
        self.assertTrue((src / "note.txt").is_file())

    def test_duplicate_and_bad_jsonl_lines(self):
        (self.tmp / "items.jsonl").write_text(
            '{"id":"1","q":"A"}\nnot json\n{"id":"1","q":"B"}\n',
            encoding="utf-8",
        )
        _items, warnings = resolve(self.tmp).decks[0].load_items()
        self.assertTrue(any("not valid JSON" in line for line in warnings))
        self.assertTrue(any("duplicate" in line for line in warnings))

    def test_required_hook_failure_writes_nothing(self):
        (self.tmp / "items.jsonl").write_text('{"id":"1","q":"A"}\n', encoding="utf-8")
        (self.tmp / "deck.json").write_text(
            json.dumps({
                "source": {"type": "jsonl", "path": "items.jsonl"},
                "hook": {"command": [sys.executable, "-c", "import sys; sys.exit(1)"], "required": True},
            }),
            encoding="utf-8",
        )
        deck = resolve(self.tmp).decks[0]
        result = decide(deck, "1", "right", None)
        self.assertFalse(result["ok"], result)
        self.assertFalse((self.tmp / ".choice" / "decisions.jsonl").exists())

    def test_library_child_error_does_not_hide_the_others(self):
        good = self.tmp / "good"
        good.mkdir()
        (good / "items.jsonl").write_text('{"id":"1","q":"Hi"}\n', encoding="utf-8")
        bad = self.tmp / "bad"
        bad.mkdir()
        (bad / "deck.json").write_text("{", encoding="utf-8")
        opened = resolve(self.tmp)
        self.assertEqual(len(opened.decks), 2)
        broken = next(deck for deck in opened.decks if deck.id == "bad")
        self.assertIsNotNone(broken.problem)

    def test_quiz_scores_when_every_answer_is_in(self):
        self._write_rows(
            [
                {"id": "1", "q": "A tomato is a fruit.", "answer": "True"},
                {"id": "2", "q": "Bats are birds.", "answer": "false"},
            ],
            {
                "title": "Quiz",
                "score": {"field": "answer"},
                "source": {"type": "jsonl", "path": "items.jsonl"},
                "show": {"body": "{{q}}", "chips": []},
                "directions": {
                    "right": {"label": "True", "value": "true"},
                    "left": {"label": "False", "value": "false"},
                    "down": {"label": "Skip", "value": "skip", "later": True},
                },
            },
        )
        deck = resolve(self.tmp).decks[0]
        decide(deck, "1", "down", None)
        waiting = progress(deck, pending=True)
        self.assertNotIn("report", waiting)
        self.assertEqual(waiting["left"], 2)
        decide(deck, "1", "right", None)
        decide(deck, "2", "left", None)
        done = progress(deck, pending=True)
        self.assertEqual(done["report"]["heading"], "2 of 2")
        self.assertEqual(done["count_label"], "2 of 2")
        self.assertEqual(done["items"], [])
        review = progress(deck, pending=False)
        self.assertEqual([item["mark"] for item in review["items"]], ["right", "right"])

    def test_round_robin_orders_by_wins_then_a_playoff(self):
        rows = [
            {"id": "a", "name": "Ash"},
            {"id": "b", "name": "Brine"},
            {"id": "c", "name": "Copper"},
        ]
        self._write_rows(rows, self._contest("robin"))
        deck = resolve(self.tmp).decks[0]
        self._beat(deck, "Ash", "Brine")
        self._beat(deck, "Ash", "Copper")
        self._beat(deck, "Brine", "Copper")
        ranked = progress(deck, pending=True)
        self.assertEqual([row["name"] for row in ranked["report"]["places"]], ["Ash", "Brine", "Copper"])
        self.assertEqual([row["note"] for row in ranked["report"]["places"]], ["2 wins", "1 win", "0 wins"])
        self.assertNotIn("playoff", ranked["report"]["detail"].lower())

        cycle = self.tmp / "cycle"
        cycle.mkdir()
        self._write_rows(rows, self._contest("robin"), folder=cycle)
        deck = resolve(cycle).decks[0]
        self._beat(deck, "Ash", "Brine")
        self._beat(deck, "Brine", "Copper")
        self._beat(deck, "Copper", "Ash")
        playoff = progress(deck, pending=True)
        self.assertEqual(playoff["count_label"], "Playoff")
        self.assertNotIn("report", playoff)
        bodies = sorted(side["body"] for side in playoff["items"][0]["sides"])
        self.assertEqual(bodies, ["Brine", "Copper"])
        self._beat(deck, "Brine", "Copper")
        self._beat(deck, "Ash", "Brine")
        ranked = progress(deck, pending=True)
        self.assertEqual([row["name"] for row in ranked["report"]["places"]], ["Ash", "Brine", "Copper"])
        self.assertIn("playoff", ranked["report"]["detail"].lower())

    def test_bracket_drops_a_loser_and_names_a_winner(self):
        rows = [
            {"id": "a", "name": "North"},
            {"id": "b", "name": "East"},
            {"id": "c", "name": "South"},
            {"id": "d", "name": "West"},
        ]
        self._write_rows(rows, self._contest("bracket"))
        deck = resolve(self.tmp).decks[0]
        opening = progress(deck, pending=True)
        self.assertEqual(opening["count_label"], "Semi-final")
        self.assertEqual(opening["total"], 3)
        self._beat(deck, "North", "East")
        self._beat(deck, "South", "West")
        final = progress(deck, pending=True)
        self.assertEqual(final["count_label"], "Final")
        self.assertEqual(len(final["items"]), 1)
        self._beat(deck, "South", "North")
        done = progress(deck, pending=True)
        self.assertEqual(done["report"]["heading"], "South")
        self.assertEqual(
            [(row["place"], row["name"]) for row in done["report"]["places"]],
            [("1", "South"), ("2", "North"), ("3", "East"), ("3", "West")],
        )
        undo(deck)
        again = progress(deck, pending=True)
        self.assertNotIn("report", again)
        self.assertEqual(again["count_label"], "Final")
        undo(deck)
        semis = progress(deck, pending=True)
        self.assertEqual(semis["count_label"], "Semi-final")
        self.assertNotIn("report", semis)

        bye = self.tmp / "bye"
        bye.mkdir()
        self._write_rows(rows[:3], self._contest("bracket"), folder=bye)
        deck = resolve(bye).decks[0]
        first = progress(deck, pending=True)
        self.assertEqual(first["count_label"], "Round 1")
        self.assertEqual(len(first["items"]), 1)
        self.assertEqual(sorted(side["body"] for side in first["items"][0]["sides"]), ["East", "South"])
        self._beat(deck, "South", "East")
        last = progress(deck, pending=True)
        self.assertEqual(last["count_label"], "Final")
        self._beat(deck, "North", "South")
        placed = progress(deck, pending=True)
        self.assertEqual([row["name"] for row in placed["report"]["places"]], ["North", "South", "East"])

    def test_story_follows_one_branch_to_an_ending(self):
        self._write_rows(
            [
                {
                    "id": "road",
                    "title": "The road",
                    "body": "A fork.",
                    "l": "Together",
                    "r": "Split",
                    "lid": "brick",
                    "rid": "straw",
                },
                {"id": "brick", "title": "Brick", "body": "The house holds."},
                {"id": "straw", "title": "Straw", "body": "The wind takes it."},
            ],
            {
                "title": "Pigs",
                "source": {"type": "jsonl", "path": "items.jsonl"},
                "show": {"title": "{{title}}", "body": "{{body}}", "chips": []},
                "story": {
                    "start": "road",
                    "left": "lid",
                    "right": "rid",
                    "labels": {"left": "l", "right": "r"},
                },
                "directions": {
                    "left": {"label": "Left", "value": "left"},
                    "right": {"label": "Right", "value": "right"},
                    "down": {"label": "Later", "value": "later", "later": True},
                },
            },
        )
        deck = resolve(self.tmp).decks[0]
        opening = progress(deck, pending=True)
        self.assertEqual(opening["items"][0]["offers"]["right"], "Split")
        self.assertEqual(opening["count_label"], "Scene 1")
        self.assertFalse(opening["meter"])
        decide(deck, "road", "left", None)
        done = progress(deck, pending=True)
        self.assertEqual(done["report"]["heading"], "Brick")
        self.assertEqual(done["report"]["detail"], "The house holds.")
        self.assertEqual([line["text"] for line in done["report"]["lines"]], ["Together"])
        self.assertEqual(done["left"], 0)
        undo(deck)
        back = progress(deck, pending=True)
        self.assertNotIn("report", back)
        self.assertEqual(back["items"][0]["id"], "road")
        decide(deck, "road", "right", None)
        other = progress(deck, pending=True)
        self.assertEqual(other["report"]["heading"], "Straw")

    def test_score_contest_and_story_do_not_combine(self):
        (self.tmp / "items.jsonl").write_text('{"id":"1","name":"Ash"}\n', encoding="utf-8")
        (self.tmp / "deck.json").write_text(
            json.dumps({
                "source": {"type": "jsonl", "path": "items.jsonl"},
                "score": {"field": "name"},
                "contest": {"kind": "robin"},
            }),
            encoding="utf-8",
        )
        with self.assertRaises(DeckProblem):
            resolve(self.tmp)
        (self.tmp / "deck.json").write_text(
            json.dumps({
                "source": {"type": "jsonl", "path": "items.jsonl"},
                "story": {"left": "lid", "right": "rid"},
                "directions": {"up": {"label": "Keep", "value": "keep"}},
            }),
            encoding="utf-8",
        )
        with self.assertRaises(DeckProblem):
            resolve(self.tmp)

    def test_each_person_has_a_log(self):
        self._write_yes_no([{"id": "1", "q": "Ready?"}])
        deck = resolve(self.tmp).decks[0]
        deck.actor = "ada"
        saved = decide(deck, "1", "right", None)
        self.assertTrue(saved["ok"], saved)
        self.assertTrue((self.tmp / ".choice" / "users" / "ada" / "decisions.jsonl").is_file())
        self.assertFalse((self.tmp / ".choice" / "decisions.jsonl").exists())
        deck.actor = "bea"
        self.assertEqual(progress(deck, pending=True)["decided"], 0)
        self.assertFalse(undo(deck)["ok"])
        deck.actor = "ada"
        self.assertEqual(progress(deck, pending=True)["decided"], 1)
        self.assertTrue(undo(deck)["ok"])
        self.assertEqual(progress(deck, pending=True)["decided"], 0)

    def test_people_file_assigns_decks(self):
        self._two_decks()
        self.assertFalse(load_roster(self.tmp).enabled)
        (self.tmp / ".choice").mkdir()
        (self.tmp / ".choice" / "users.json").write_text(
            json.dumps({
                "users": [
                    {"name": "Ada", "decks": ["yes-no"]},
                    {"id": "bea", "name": "Bea", "decks": "*"},
                ],
                "extra": True,
            }),
            encoding="utf-8",
        )
        roster = load_roster(self.tmp)
        self.assertTrue(roster.enabled)
        self.assertTrue(any("unknown key" in line for line in roster.warnings))
        ada = roster.get("ada")
        self.assertEqual(ada.decks, ["yes-no"])
        self.assertFalse(ada.sees("pigs"))
        self.assertTrue(roster.get("bea").sees("pigs"))
        self.assertEqual(
            assignment_warnings([Person("ada", "Ada", ["gone"])], {"yes-no", "pigs"}),
            ["Ada: no deck 'gone'"],
        )
        (self.tmp / ".choice" / "users.json").write_text("{", encoding="utf-8")
        with self.assertRaises(DeckProblem):
            load_roster(self.tmp)
        with self.assertRaises(DeckProblem):
            parse_users([{"name": "Ada", "decks": ["gone"]}], {"yes-no", "pigs"})
        opened = resolve(self.tmp)
        (self.tmp / ".choice" / "users.json").write_text(
            json.dumps({"users": [{"id": "ada", "name": "Ada", "decks": ["yes-no"]}]}),
            encoding="utf-8",
        )
        roster = load_roster(self.tmp)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _print_tally(opened.decks, roster)
        text = buf.getvalue()
        self.assertIn("Ada", text)
        self.assertIn("Not assigned.", text)

    def test_http_people_assign_decks(self):
        self._two_decks()
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            made = self._post(port, "/api/users", {"users": [
                {"name": "Ada", "decks": ["yes-no"]},
                {"name": "Bea", "decks": ["pigs"]},
            ]})
            self.assertEqual(made.status, 200, made.body)
            saved = json.loads(made.body)
            self.assertEqual([user["id"] for user in saved["users"]], ["ada", "bea"])
            picker = self._get(port, "/api/index")
            self.assertTrue(picker["pick"])
            self.assertEqual(picker["decks"], [])
            self.assertEqual(sorted(row["id"] for row in picker["library"]), ["pigs", "yes-no"])
            ada = self._get(port, "/api/index?user=ada")
            self.assertEqual([row["id"] for row in ada["decks"]], ["yes-no"])
            missing = self._post(port, "/api/decks/yes-no/decide", {"item": "1", "direction": "right"})
            self.assertEqual(missing.status, 400, missing.body)
            denied = self._post(port, "/api/decks/yes-no/decide", {"item": "1", "direction": "right", "user": "bea"})
            self.assertEqual(denied.status, 403, denied.body)
            kept = self._post(port, "/api/decks/yes-no/decide", {"item": "1", "direction": "right", "user": "ada"})
            self.assertEqual(kept.status, 200, kept.body)
            pigs = self._get(port, "/api/decks/pigs/items?pending=1&user=bea")
            self.assertEqual(pigs["left"], 1)
            self.assertTrue((self.tmp / "yes-no" / ".choice" / "users" / "ada" / "decisions.jsonl").is_file())
            self.assertFalse((self.tmp / "yes-no" / ".choice" / "decisions.jsonl").exists())
            bad = self._post(port, "/api/users", {"users": [{"name": "Ada", "decks": ["gone"]}]})
            self.assertEqual(bad.status, 400, bad.body)
            self.assertTrue((self.tmp / ".choice" / "users.json").is_file())
            cleared = self._post(port, "/api/users", {"users": []})
            self.assertEqual(cleared.status, 200, cleared.body)
            self.assertFalse((self.tmp / ".choice" / "users.json").exists())
            shared = self._get(port, "/api/index")
            self.assertIsNone(shared["users"])
            self.assertEqual(len(shared["decks"]), 2)
        finally:
            server.shutdown()
            server.server_close()

    def test_http_roundtrip(self):
        self._write_yes_no([{"id": "1", "n": "1", "q": "Ready?"}])
        ChoiceSite.allow_reuse_address = True
        server = ChoiceSite(("127.0.0.1", 0), self.tmp)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            index = self._get(port, "/api/index")
            self.assertTrue(index["ok"])
            self.assertEqual(index["decks"][0]["left"], 1)
            page = urllib.request.urlopen("http://127.0.0.1:%s/" % port)
            self.assertIn(b"Choice", page.read())
            denied = self._post(port, "/api/decks/yes-no/decide", {"item": "1", "direction": "right"}, ctype="text/plain")
            self.assertEqual(denied.status, 415)
            # The folder slug is the temp directory name, not yes-no.
            deck_id = index["decks"][0]["id"]
            saved = self._post(port, "/api/decks/%s/decide" % deck_id, {"item": "1", "direction": "right", "note": "ok"})
            self.assertEqual(saved.status, 200, saved.body)
            items = self._get(port, "/api/decks/%s/items?pending=1" % deck_id)
            self.assertEqual(items["left"], 0)
            media = self._open(port, "/api/decks/%s/media?item=.." % deck_id)
            self.assertEqual(media.status, 404)
        finally:
            server.shutdown()
            server.server_close()

    def _open(self, port, path):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%s%s" % (port, path)) as res:
                return _Response(res.status, res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return _Response(exc.code, exc.read().decode("utf-8"))

    def _contest(self, kind):
        return {
            "title": kind,
            "contest": {"kind": kind, "name": "name"},
            "source": {"type": "jsonl", "path": "items.jsonl"},
            "directions": {
                "left": {"label": "Left", "value": "left"},
                "right": {"label": "Right", "value": "right"},
            },
        }

    def _write_rows(self, rows, config, folder=None):
        root = folder or self.tmp
        (root / "items.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        (root / "deck.json").write_text(json.dumps(config), encoding="utf-8")

    def _beat(self, deck, winner, loser):
        snap = progress(deck, pending=True)
        for item in snap["items"]:
            sides = [side["body"] for side in item["sides"]]
            if winner not in sides or loser not in sides:
                continue
            direction = "left" if item["sides"][0]["body"] == winner else "right"
            result = decide(deck, item["id"], direction, None)
            self.assertTrue(result["ok"], result)
            return
        self.fail("no match %s vs %s" % (winner, loser))

    def _two_decks(self):
        for name in ("yes-no", "pigs"):
            folder = self.tmp / name
            folder.mkdir()
            (folder / "items.jsonl").write_text('{"id":"1","q":"Ready?"}\n', encoding="utf-8")
            (folder / "deck.json").write_text(
                json.dumps({
                    "title": name,
                    "source": {"type": "jsonl", "path": "items.jsonl"},
                    "show": {"body": "{{q}}"},
                }),
                encoding="utf-8",
            )

    def _write_yes_no(self, rows):
        (self.tmp / "items.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        (self.tmp / "deck.json").write_text(
            json.dumps({
                "title": "Yes or no",
                "source": {"type": "jsonl", "path": "items.jsonl"},
                "show": {"body": "{{q}}"},
                "directions": {
                    "right": {"label": "Yes", "value": "yes"},
                    "left": {"label": "No", "value": "no"},
                    "down": {"label": "Skip", "value": "skip", "later": True},
                },
            }),
            encoding="utf-8",
        )

    def _get(self, port, path):
        with urllib.request.urlopen("http://127.0.0.1:%s%s" % (port, path)) as res:
            return json.load(res)

    def _post(self, port, path, payload, ctype="application/json"):
        req = urllib.request.Request(
            "http://127.0.0.1:%s%s" % (port, path),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": ctype},
        )
        try:
            with urllib.request.urlopen(req) as res:
                return _Response(res.status, res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return _Response(exc.code, exc.read().decode("utf-8"))


class _Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body


if __name__ == "__main__":
    unittest.main()
