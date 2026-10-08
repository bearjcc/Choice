# SPDX-License-Identifier: AGPL-3.0-only
"""Piles that change as you swipe.

score: the swipe value is checked against a field. One point each.
  The score appears when every answered card has been decided.

contest robin: every pair of rows meets once. Order is by wins.
  Two names with the same wins are split by the match between them.
  A group that is still tied (a cycle, for example) plays a playoff.
  The playoff does not add wins. Winners of a playoff match rank above
  the losers, and that continues until that group has an order.
  An odd name at the start of a round waits.

contest bracket: the list order is the bracket. First plays second.
  Lose and you are out. Win and you go to the next round.
  An odd name waits, and that waiting name is the first one still in.
  Names that lose in the same round share the next place.

story: each row is a scene. A swipe names the next scene.
  A scene with no next id is the ending, and it is not a swipe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from choice.load import Deck, Item, Side
from choice.rated import Player, confidence, pick_pair, ranking
from choice.rated import update as rated_update


@dataclass
class Flow:
    items: list
    warnings: list = field(default_factory=list)
    report: dict | None = None
    total: int | None = None
    decided: int | None = None
    left: int | None = None
    count_label: str | None = None
    meter: bool | None = None
    marks: dict = field(default_factory=dict)
    replay: bool | None = None
    choices: dict = field(default_factory=dict)


@dataclass
class _Player:
    id: str
    name: str
    path: object = None
    media_token: str = ""


@dataclass
class _Game:
    id: str
    a: str
    b: str
    title: str
    winner: str = ""
    loser: str = ""
    round_label: str = ""


def arrange(deck: Deck, items: list[Item], choices: dict) -> Flow:
    if deck.contest_kind == "taste":
        return _taste(deck, items, choices)
    if deck.contest_kind == "rated":
        return _rated(deck, items, choices)
    if deck.contest_kind == "robin":
        return _robin(deck, items, choices)
    if deck.contest_kind == "bracket":
        return _bracket(deck, items, choices)
    if deck.story:
        return _story(deck, items, choices)
    if deck.score_field:
        return _score(deck, items, choices)
    return Flow(list(items))


def report_lines(report: dict | None) -> list[str]:
    if not report:
        return []
    lines = [report.get("heading") or ""]
    detail = report.get("detail") or ""
    if detail:
        lines.append(detail)
    for row in report.get("places") or []:
        note = " (%s)" % row["note"] if row.get("note") else ""
        lines.append("%s. %s%s" % (row.get("place"), row.get("name"), note))
    for row in report.get("lines") or []:
        prefix = {"right": "Correct", "wrong": "Missed"}.get(row.get("mark") or "", "")
        text = row.get("text") or ""
        note = " (%s)" % row["note"] if row.get("note") else ""
        if prefix:
            lines.append("%s: %s%s" % (prefix, text, note))
        elif text:
            lines.append(text)
    return lines


def _score(deck: Deck, items: list[Item], choices: dict) -> Flow:
    field_name = deck.score_field or ""
    marks = {}
    lines = []
    warnings = []
    correct = 0
    pending = 0
    scored = 0
    for item in items:
        answer = str(item.fields.get(field_name) or "").strip()
        if not answer:
            warnings.append("score: '%s' has no answer" % item.id)
            continue
        scored += 1
        choice = choices.get(item.id)
        if not choice or choice.get("later"):
            pending += 1
            continue
        got = str(choice.get("value") or "").strip()
        right = got.casefold() == answer.casefold()
        if right:
            correct += 1
        mark = "right" if right else "wrong"
        note = "Answer: %s" % answer
        marks[item.id] = {"mark": mark, "note": note}
        lines.append({"text": item.body or item.title, "mark": mark, "note": note})
    report = None
    count_label = None
    if scored and not pending:
        report = {
            "kind": "score",
            "heading": "%d of %d" % (correct, scored),
            "detail": "One point for each correct answer.",
            "lines": lines,
        }
        count_label = report["heading"]
    return Flow(list(items), warnings=warnings, report=report, marks=marks, count_label=count_label)


def _story(deck: Deck, items: list[Item], choices: dict) -> Flow:
    if not items:
        return Flow([])
    spec = deck.story or {}
    by_id = {item.id: item for item in items}
    warnings = []
    start = spec.get("start") or items[0].id
    if start not in by_id:
        warnings.append("story: start '%s' is not a card. Starting at the first row." % start)
        start = items[0].id

    path: list[Item] = []
    seen: set[str] = set()
    node = start
    ending = None
    missing = ""
    looped = ""
    while node:
        if node in seen:
            looped = node
            warnings.append("story: '%s' loops back." % node)
            break
        item = by_id.get(node)
        if item is None:
            missing = node
            warnings.append("story: next scene '%s' is not in the pile." % node)
            break
        seen.add(node)
        _offer(deck, item)
        if _is_ending(spec, item):
            ending = item
            break
        path.append(item)
        choice = choices.get(item.id)
        if not choice or choice.get("later"):
            break
        direction = str(choice.get("direction") or "")
        field_name = (spec.get("next") or {}).get(direction) or ""
        node = str(item.fields.get(field_name) or "").strip() if field_name else ""
        if node:
            continue
        missing = item.id
        warnings.append("story: '%s' does not name a next scene." % item.id)
        break

    if ending is None and not missing and not looped:
        return Flow(path, warnings=warnings, count_label="Scene %d" % len(path), meter=False, replay=True)

    report = _story_report(ending, missing, looped, path, choices)
    label = ending.title if ending is not None else report["heading"]
    flow = Flow(
        path,
        warnings=warnings,
        report=report,
        count_label=label,
        meter=True,
        replay=bool(path),
    )
    if not path:
        flow.total, flow.decided, flow.left = 1, 1, 0
    return flow


def _story_report(ending, missing: str, looped: str, path: list[Item], choices: dict) -> dict:
    lines = []
    for item in path:
        choice = choices.get(item.id)
        if choice and not choice.get("later"):
            lines.append({"text": choice.get("label") or choice.get("value") or item.title})
    if ending is not None:
        return {"kind": "story", "heading": ending.title or "The end", "detail": ending.body, "lines": lines}
    if missing:
        return {"kind": "story", "heading": "That scene is missing", "detail": missing, "lines": lines}
    return {
        "kind": "story",
        "heading": "This path loops",
        "detail": "Scene %s points back at an earlier scene." % looped,
        "lines": lines,
    }


def _offer(deck: Deck, item: Item) -> None:
    spec = deck.story or {}
    offers = {}
    picks = {}
    labels = {}
    for direction, field_name in (spec.get("next") or {}).items():
        nxt = str(item.fields.get(field_name) or "").strip()
        if not nxt:
            offers[direction] = ""
            continue
        label_field = (spec.get("labels") or {}).get(direction) or ""
        label = str(item.fields.get(label_field) or "").strip() if label_field else ""
        if not label:
            action = deck.directions.get(direction)
            label = action.label if action else direction
        offers[direction] = label
        picks[direction] = nxt
        labels[direction] = label
    item.offers = offers
    item.picks = picks
    item.pick_labels = labels


def _is_ending(spec: dict, item: Item) -> bool:
    for field_name in (spec.get("next") or {}).values():
        if str(item.fields.get(field_name) or "").strip():
            return False
    return True


def _players(deck: Deck, items: list[Item]) -> list[_Player]:
    found = []
    for item in items:
        name = item.fields.get(deck.contest_name) or item.title or item.id
        image = item.path if item.kind == "image" else None
        found.append(_Player(item.id, str(name), image, item.media_token if image else ""))
    return found


def _robin(deck: Deck, items: list[Item], choices: dict) -> Flow:
    players = _players(deck, items)
    if not players:
        return Flow([])
    if len(players) == 1:
        return _solo(players[0])
    by_id = {player.id: player for player in players}
    order = [player.id for player in players]
    games = _robin_games(order)
    done = []
    for game in games:
        winner = _winner(choices.get(game.id), game.a, game.b)
        if winner:
            game.winner = winner
            game.loser = game.b if winner == game.a else game.a
            done.append(game)
    robin_n = len(games)
    if len(done) < robin_n:
        return Flow(
            [_match_item(game, by_id) for game in games],
            total=robin_n,
            decided=len(done),
            left=robin_n - len(done),
            replay=True,
        )

    wins = {pid: 0 for pid in order}
    for game in done:
        wins[game.winner] += 1
    results = [(game.a, game.b, game.winner) for game in done]
    units, used_playoff, split_h2h = _rank_units(order, wins, results)
    clusters = [unit for unit in units if isinstance(unit, list)]
    playoff_known: list[_Game] = []
    playoff_pending: list[_Game] = []
    orders = {}
    for cluster in clusters:
        known, pending, ordered = _total_order(cluster, choices, "p:" + _group_key(cluster))
        playoff_known.extend(known)
        playoff_pending.extend(pending)
        if ordered is not None:
            orders[_group_key(cluster)] = ordered

    cards = [_match_item(game, by_id) for game in games + playoff_known]
    extra = sum(_order_len(len(cluster)) for cluster in clusters)
    if playoff_pending or len(orders) < len(clusters):
        total = robin_n + extra
        decided = robin_n + (len(playoff_known) - len(playoff_pending))
        return Flow(
            cards,
            total=total,
            decided=decided,
            left=total - decided,
            count_label="Playoff",
            replay=True,
        )

    places = _stitch(units, orders, by_id, wins)
    return Flow(
        cards,
        report={
            "kind": "rank",
            "heading": "Your order",
            "detail": _robin_detail(used_playoff, split_h2h),
            "places": places,
        },
        total=robin_n + len(playoff_known),
        decided=robin_n + len(playoff_known),
        left=0,
        count_label=places[0]["name"] if places else None,
        replay=True,
    )


def _bracket(deck: Deck, items: list[Item], choices: dict) -> Flow:
    players = _players(deck, items)
    if not players:
        return Flow([])
    if len(players) == 1:
        return _solo(players[0])
    by_id = {player.id: player for player in players}
    remaining = [player.id for player in players]
    known: list[_Game] = []
    groups: list[tuple[str, list[str]]] = []
    round_no = 1
    games_total = len(players) - 1
    while len(remaining) > 1:
        byes, pairs = _split(remaining)
        label = _round_label(len(pairs), len(byes), round_no)
        winners = list(byes)
        losers = []
        pending = False
        for a, b in pairs:
            game = _Game(_mid("b:r%d" % round_no, a, b), a, b, label, round_label=label)
            known.append(game)
            winner = _winner(choices.get(game.id), a, b)
            if not winner:
                pending = True
                continue
            game.winner = winner
            game.loser = b if winner == a else a
            winners.append(winner)
            losers.append(game.loser)
        if pending:
            done = sum(1 for game in known if game.winner)
            return Flow(
                [_match_item(game, by_id) for game in known],
                total=games_total,
                decided=done,
                left=games_total - done,
                count_label=label,
                replay=True,
            )
        if losers:
            groups.append((label, losers))
        remaining = winners
        round_no += 1

    champion = remaining[0]
    places = [{"place": "1", "name": by_id[champion].name, "note": "Winner"}]
    next_place = 2
    for label, losers in reversed(groups):
        for loser in losers:
            places.append({
                "place": str(next_place),
                "name": by_id[loser].name,
                "note": _out_note(label),
            })
        next_place += len(losers)
    return Flow(
        [_match_item(game, by_id) for game in known],
        report={
            "kind": "rank",
            "heading": by_id[champion].name,
            "detail": "Lose a match and you are out. Names that lost in the same round share a place.",
            "places": places,
        },
        total=games_total,
        decided=games_total,
        left=0,
        count_label=by_id[champion].name,
        replay=True,
    )


def _solo(player: _Player) -> Flow:
    return Flow(
        [],
        report={
            "kind": "rank",
            "heading": "Your order",
            "detail": "By wins.",
            "places": [{"place": "1", "name": player.name}],
        },
        total=1,
        decided=1,
        left=0,
        count_label=player.name,
        replay=False,
    )


def _robin_games(ids: list[str]) -> list[_Game]:
    """Circle schedule. Everyone sits out at most one match in a round."""
    seats = list(ids)
    if len(seats) % 2 == 1:
        seats.append("")
    count = len(seats)
    games = []
    seen = set()
    for _round in range(count - 1):
        for index in range(count // 2):
            a = seats[index]
            b = seats[count - 1 - index]
            if not a or not b:
                continue
            game = _Game(_mid("m", a, b), a, b, "Which ranks higher?")
            if game.id in seen:
                continue
            seen.add(game.id)
            games.append(game)
        seats = [seats[0], seats[-1], *seats[1:-1]]
    return games


def _rank_units(order: list[str], wins: dict, results: list[tuple[str, str, str]]):
    buckets: dict[int, list[str]] = {}
    for pid in order:
        buckets.setdefault(wins[pid], []).append(pid)
    units = []
    used_playoff = False
    split_h2h = False
    for key in sorted(buckets, reverse=True):
        group = buckets[key]
        if len(group) > 1:
            split_h2h = True
        for unit in _tiebreak(group, results):
            if isinstance(unit, list):
                used_playoff = True
            units.append(unit)
    if used_playoff:
        split_h2h = any(len(group) > 1 and not _still_tied(group, results) for group in buckets.values())
    return units, used_playoff, split_h2h


def _still_tied(group: list[str], results) -> bool:
    if len(group) <= 1:
        return False
    scores = _within(group, results)
    return len(set(scores.values())) == 1


def _tiebreak(group: list[str], results):
    if len(group) <= 1:
        return list(group)
    scores = _within(group, results)
    if len(set(scores.values())) == 1:
        return [list(group)]
    buckets: dict[int, list[str]] = {}
    for pid in group:
        buckets.setdefault(scores[pid], []).append(pid)
    units = []
    for key in sorted(buckets, reverse=True):
        bucket = buckets[key]
        if len(bucket) == 1:
            units.append(bucket[0])
            continue
        units.extend(_tiebreak(bucket, results))
    return units


def _within(group: list[str], results) -> dict:
    wanted = set(group)
    scores = {pid: 0 for pid in group}
    for a, b, winner in results:
        if a in wanted and b in wanted and winner in scores:
            scores[winner] += 1
    return scores


def _total_order(ids: list[str], choices: dict, prefix: str):
    """Order a tied group. Returns known games, pending games, and the order."""
    if len(ids) <= 1:
        return [], [], list(ids)
    byes, pairs = _split(ids)
    known = []
    winners = list(byes)
    losers = []
    pending = []
    for a, b in pairs:
        game = _Game(_mid(prefix, a, b), a, b, "Playoff")
        known.append(game)
        winner = _winner(choices.get(game.id), a, b)
        if not winner:
            pending.append(game)
            continue
        game.winner = winner
        game.loser = b if winner == a else a
        winners.append(winner)
        losers.append(game.loser)
    if pending:
        return known, pending, None
    w_known, w_pending, w_order = _total_order(winners, choices, prefix)
    l_known, l_pending, l_order = _total_order(losers, choices, prefix)
    known.extend(w_known)
    known.extend(l_known)
    if w_order is None or l_order is None:
        return known, w_pending + l_pending, None
    return known, [], w_order + l_order


def _order_len(count: int) -> int:
    if count <= 1:
        return 0
    pairs = count // 2
    byes = count % 2
    return pairs + _order_len(pairs + byes) + _order_len(pairs)


def _stitch(units, orders: dict, by_id: dict, wins: dict) -> list[dict]:
    placed = []
    for unit in units:
        if isinstance(unit, list):
            placed.extend(orders.get(_group_key(unit)) or [])
            continue
        placed.append(unit)
    rows = []
    for index, pid in enumerate(placed, start=1):
        rows.append({
            "place": str(index),
            "name": by_id[pid].name,
            "note": _win_note(wins.get(pid, 0)),
        })
    return rows


def _robin_detail(used_playoff: bool, split_h2h: bool) -> str:
    if used_playoff:
        return "By wins. A playoff ordered the names that were still tied."
    if split_h2h:
        return "By wins. A tie breaks on the matches between those names."
    return "By wins."


def _split(ids: list[str]):
    """Pair neighbours. If one name is left over, the first one waits."""
    rest = list(ids)
    byes = []
    if len(rest) % 2 == 1:
        byes.append(rest.pop(0))
    pairs = [(rest[index], rest[index + 1]) for index in range(0, len(rest), 2)]
    return byes, pairs


def _round_label(n_matches: int, n_byes: int, round_no: int) -> str:
    if n_matches == 1 and n_byes == 0:
        return "Final"
    if n_matches == 2 and n_byes == 0:
        return "Semi-final"
    if n_matches == 4 and n_byes == 0:
        return "Quarter-final"
    return "Round %d" % round_no


def _out_note(label: str) -> str:
    if label in {"Final", "Semi-final", "Quarter-final"}:
        return "Out in the %s" % label.lower()
    lowered = label[:1].lower() + label[1:]
    return "Out in %s" % lowered


def _win_note(count: int) -> str:
    if count == 1:
        return "1 win"
    return "%d wins" % count


def _winner(choice: dict | None, a: str, b: str) -> str:
    if not choice or choice.get("later"):
        return ""
    value = str(choice.get("value") or "")
    if value == a or value == b:
        return value
    return ""


def _match_item(game: _Game, by_id: dict) -> Item:
    a = by_id[game.a]
    b = by_id[game.b]
    return Item(
        id=game.id,
        kind="pair",
        title=game.title,
        body="",
        sides=[_side("a", a), _side("b", b)],
        fields={"a": a.id, "b": b.id},
        offers={"left": a.name, "right": b.name},
        picks={"left": a.id, "right": b.id},
        pick_labels={"left": a.name, "right": b.name},
    )


def _side(key: str, player: _Player) -> Side:
    if player.path is not None:
        return Side(key=key, label=player.name, body="", path=player.path, media_token=player.media_token)
    return Side(key=key, label="", body=player.name)


def _mid(prefix: str, a: str, b: str) -> str:
    x, y = (a, b) if str(a) <= str(b) else (b, a)
    return "%s:%s:%s" % (prefix, _tag(x), _tag(y))


def _tag(text: str) -> str:
    return "%d.%s" % (len(str(text)), text)


def _group_key(ids: list[str]) -> str:
    return ".".join(_tag(pid) for pid in sorted(ids, key=str))


def _taste(deck: Deck, items: list[Item], choices: dict) -> Flow:
    """Stage 1: yes/no filter. Stage 2: rank likes (robin/bracket/rated by size)."""
    pending = [it for it in items if it.id not in choices or choices[it.id].get("later")]
    if pending:
        return Flow(
            pending,
            total=len(items),
            decided=len(items) - len(pending),
            left=len(pending),
            count_label="Filter",
            meter=True,
        )
    likes = []
    for item in items:
        record = choices.get(item.id) or {}
        value = str(record.get("value") or "").lower()
        if value in {"yes", "keep", "right", "like", "y"}:
            likes.append(item)
    if len(likes) <= 8:
        sub = Deck(
            id=deck.id,
            title=deck.title,
            root=deck.root,
            state_dir=deck.state_dir,
            directions=deck.directions,
            buttons=deck.buttons,
            blind=deck.blind,
            warnings=deck.warnings,
            contest_kind="bracket" if len(likes) > 2 else None,
            _load=lambda: (likes, []),
        )
        if len(likes) <= 2:
            return Flow(likes, report={"heading": "Likes", "places": [{"place": i + 1, "name": it.title} for i, it in enumerate(likes)]})
        if len(likes) <= 12:
            sub.contest_kind = "robin"
            return _robin(sub, likes, choices)
        return _bracket(sub, likes, choices)
    sub = Deck(
        id=deck.id,
        title=deck.title,
        root=deck.root,
        state_dir=deck.state_dir,
        directions=deck.directions,
        buttons=deck.buttons,
        blind=deck.blind,
        warnings=deck.warnings,
        contest_kind="rated",
        _load=lambda: (likes, []),
    )
    return _rated(sub, likes, choices)


def _rated(deck: Deck, items: list[Item], choices: dict) -> Flow:
    by_id = {item.id: item for item in items}
    players = {item.id: Player(id=item.id) for item in items}
    decided_pairs: set[tuple[str, str]] = set()
    for item in items:
        if item.kind != "pair":
            continue
        choice = choices.get(item.id)
        if not choice or choice.get("later"):
            continue
        a = str(item.fields.get("a") or "")
        b = str(item.fields.get("b") or "")
        winner = str(choice.get("value") or "")
        if winner in {a, b} and a and b:
            key = tuple(sorted((a, b)))
            decided_pairs.add(key)
            loser = b if winner == a else a
            if winner in players and loser in players:
                rated_update(players, winner, loser)
    pair = pick_pair(players, decided_pairs)
    visible: list[Item] = []
    if pair:
        a, b = pair
        game = _Game(id=_mid("rated", a, b), a=a, b=b, title="Which do you prefer?")
        visible.append(_match_item(game, {pid: _Player(pid, by_id[pid].title, by_id[pid].path, by_id[pid].media_token) for pid in (a, b)}))
    conf = confidence(players)
    places = [
        {"place": idx + 1, "name": by_id[pid].title if pid in by_id else pid, "note": "RD %.0f" % rd}
        for idx, (pid, _rating, rd) in enumerate(ranking(players)[:10])
    ]
    report = None
    if not pair and decided_pairs:
        report = {"heading": "Rated ranking", "places": places}
    return Flow(
        visible,
        total=max(len(decided_pairs) + (1 if pair else 0), 1),
        decided=len(decided_pairs),
        left=1 if pair else 0,
        count_label="Rated %.0f%%" % (conf * 100),
        meter=True,
        report=report,
        choices=choices,
    )
