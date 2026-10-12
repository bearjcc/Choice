# tests

Run the Python suite from the repo root:

```
python -m pytest -q
```

CI sets `CHOICE_SYNC_WORK=1` and `CHOICE_DISABLE_WARM=1` for deterministic timing.

Browser layout checks (Node, no install required for the small `.mjs` units):

```
node tests/web/action_icons.test.mjs
node tests/web/dialog_layout.test.mjs
```

Playwright UI review (`tests/test_web_ui_review.py`) runs only when `CHOICE_RUN_PLAYWRIGHT=1` and browsers are installed locally.
