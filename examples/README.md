# Examples

`python -m choice examples` lists these.

- `yes-no`: four text cards. Yes, No, Favourite, Skip.
- `which-one`: two A/B cards. On a wide window the two answers sit side by side. Blind is on, so the answer in `real` stays in Details until you turn Blind off. `hook.py` shows how to copy swipes into another file. It is not switched on.
- `photos`: two pictures. Left moves a file into `.choice/trash`. Undo puts it back.
- `immich`: two stand-in pictures. Left is Bin, up is Favourite. `hook.py` tells an Immich server, using the card id as the asset id. It is not switched on. Set `IMMICH_URL` and `IMMICH_API_KEY` before you turn it on. The pictures stay where they are. Choice does not download your library.
- `true-false`: eight statements. Right is True, left is False. Blind hides the answer until the end, when the page shows how many you got.
- `round-robin`: five bakeries. Every pair meets once, then you get an order from first to last. A tie that the matches cannot break becomes a playoff.
- `knockout`: eight shelters. Lose and you are out. Win and you go to the next round. The end is a placing, and the last one standing is first.
- `pigs`: a short telling of the three little pigs. Left and right are the two things you can do. Neither one is marked correct. The scene you reach is the ending.

Swiping here writes `.choice/` inside the example folder. That folder is gitignored. Delete it to reset the pile.
