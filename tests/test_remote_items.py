# SPDX-License-Identifier: AGPL-3.0-only

import unittest

from choice.sources.remote_items import (
    feed_entry_item,
    feed_entry_preview,
    immich_deck_item,
    immich_preview_item,
    webdav_deck_item,
    webdav_href_id,
    webdav_preview_item,
)


class RemoteItemsTests(unittest.TestCase):
    def test_immich_preview_matches_deck(self):
        asset = {
            "id": "abc-123",
            "originalFileName": "holiday.jpg",
            "type": "IMAGE",
        }
        preview = immich_preview_item(asset)
        deck = immich_deck_item(asset)
        self.assertEqual(preview.id, deck.id)
        self.assertEqual(preview.title, deck.title)
        self.assertEqual(preview.kind, deck.kind)
        self.assertEqual(deck.fields["immich_id"], preview.id)
        self.assertTrue(deck.plugin_media)

        video = dict(asset, type="VIDEO")
        self.assertEqual(immich_preview_item(video).kind, "video")
        self.assertEqual(immich_deck_item(video).kind, "video")

    def test_feed_entry_preview_matches_deck(self):
        entry = {
            "id": "entry-1",
            "title": "Hello",
            "body": "x" * 300,
            "link": "https://example.com/p",
        }
        preview = feed_entry_preview(entry)
        deck = feed_entry_item(entry)
        self.assertEqual(preview.id, deck.id)
        self.assertEqual(preview.title, deck.title)
        self.assertEqual(preview.kind, deck.kind)
        self.assertEqual(preview.body, entry["body"][:200])
        self.assertEqual(deck.body, entry["body"])
        self.assertEqual(deck.fields["link"], entry["link"])

    def test_webdav_preview_matches_deck(self):
        href = "/photos/vacation/beach.jpg"
        preview = webdav_preview_item(href)
        deck = webdav_deck_item(href)
        item_id = webdav_href_id(href)
        self.assertEqual(preview.id, item_id)
        self.assertEqual(deck.id, item_id)
        self.assertEqual(preview.title, "beach.jpg")
        self.assertEqual(deck.title, preview.title)
        self.assertEqual(preview.kind, "image")
        self.assertEqual(deck.media_token, href)
        self.assertEqual(deck.fields["href"], href)


if __name__ == "__main__":
    unittest.main()
