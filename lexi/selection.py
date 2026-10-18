"""Daily vocabulary selection, independent of Flask and HTML.

The same rules are implemented in static/js/selection.js for offline use.
See docs/SELECTION.md for the portable algorithm and its limits.
"""

from datetime import date

EPOCH = date(2025, 1, 1)


def build_deck(collections, words, selected_ids):
    """Interleave the selected collections in their metadata order.

    Exhausted collections are skipped. Each word occurs exactly once in a deck.
    JSON array order is intentional and must be preserved on other platforms.
    """
    selected = set(selected_ids)
    known = {collection["id"] for collection in collections}
    if not selected or not selected <= known:
        raise ValueError("Select at least one valid collection.")
    buckets = [
        [word for word in words if word["collectionId"] == collection["id"]]
        for collection in collections
        if collection["id"] in selected
    ]
    if any(not bucket for bucket in buckets):
        raise ValueError("A selected collection has no words.")
    return [
        bucket[index]
        for index in range(max(map(len, buckets)))
        for bucket in buckets
        if index < len(bucket)
    ]


def select_word(collections, words, selected_ids, day):
    """Return one deterministic word for an ISO calendar day."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    deck = build_deck(collections, words, selected_ids)
    return deck[(day - EPOCH).days % len(deck)]

