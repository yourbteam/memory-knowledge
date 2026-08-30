#!/usr/bin/env python3
"""Transfer rule lineage only when a merge chain has one final survivor."""

from __future__ import annotations

import copy


def reduce(source_items: list[dict], pairs: list[tuple[int, int]], ratio_limit: int = 2) -> dict:
    items = copy.deepcopy(source_items)
    outgoing = {number: set() for number in range(1, len(items) + 1)}
    owner_pairs: list[tuple[int, int]] = []

    for left_number, right_number in pairs:
        if not (1 <= left_number <= len(items) and 1 <= right_number <= len(items)):
            raise ValueError(
                f"merge pair {(left_number, right_number)!r} is outside 1..{len(items)}"
            )
        left, right = items[left_number - 1], items[right_number - 1]
        shorter = min(len(left["text"]), len(right["text"]))
        if shorter == 0:
            raise ValueError(f"merge pair {(left_number, right_number)!r} contains empty text")
        if max(len(left["text"]), len(right["text"])) > ratio_limit * shorter:
            owner_pairs.append((left_number, right_number))
            continue
        keeper, dropped = (
            (left_number, right_number)
            if len(left["text"]) >= len(right["text"])
            else (right_number, left_number)
        )
        outgoing[dropped].add(keeper)

    def sinks(number: int, trail: tuple[int, ...] = ()) -> set[int]:
        if number in trail:
            return set()
        if not outgoing[number]:
            return {number}
        return set().union(
            *(sinks(next_number, trail + (number,)) for next_number in outgoing[number])
        )

    groups: dict[int, list[int]] = {}
    ambiguous: list[dict] = []
    for number in range(1, len(items) + 1):
        destinations = sinks(number)
        if len(destinations) == 1:
            destination = next(iter(destinations))
        else:
            destination = number
            ambiguous.append(
                {"source_rule_id": number, "possible_terminal_rule_ids": sorted(destinations)}
            )
            owner_pairs.extend((number, terminal) for terminal in sorted(destinations))
        groups.setdefault(destination, []).append(number)

    reduced: list[tuple[int, dict]] = []
    components: list[dict] = []
    for keeper, members in groups.items():
        item = copy.deepcopy(items[keeper - 1])
        item["pages"] = sorted(
            {page for number in members for page in items[number - 1].get("pages", [])}
        )
        source_rule_ids = sorted(
            {
                source_id
                for number in members
                for source_id in items[number - 1].get("source_rule_ids", [number])
            }
        )
        item["source_rule_ids"] = source_rule_ids
        aliases: list[str] = []
        for number in members:
            candidate = items[number - 1]
            if number != keeper:
                aliases.append(candidate["text"])
            aliases.extend(candidate.get("also_stated_as", []))
        aliases = list(dict.fromkeys(alias for alias in aliases if alias != item["text"]))
        if aliases:
            item["also_stated_as"] = aliases
        else:
            item.pop("also_stated_as", None)
        reduced.append((min(members), item))
        components.append(
            {
                "member_rule_ids": sorted(members),
                "keeper_rule_id": keeper,
                "source_rule_ids": source_rule_ids,
            }
        )

    return {
        "items": [item for _, item in sorted(reduced)],
        "owner_pairs": sorted(set(owner_pairs)),
        "ambiguous": ambiguous,
        "components": sorted(components, key=lambda component: component["member_rule_ids"][0]),
    }
