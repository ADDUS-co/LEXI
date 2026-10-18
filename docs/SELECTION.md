# Daily selection contract / Android preparation

This version-1 content and selection contract is not an Android app.

## Inputs

- Ordered collection metadata with unique stable IDs in `collections.json`.
- Ordered word entries with unique IDs and valid collection references in `words.json`.
- A nonempty set of selected collection IDs. Selection-click order and duplicates do not affect the result.
- A calendar date in the configured IANA timezone: `Asia/Bishkek` (UTC+6) by default. Device clocks must be accurate for offline use.
- Fixed epoch: `2025-01-01`, a calendar date, not an instant in the device's timezone.

## Algorithm

1. Traverse selected collections in metadata-array order.
2. Take each collection's words in word-array order.
3. Interleave: first word from each collection, then second from each, etc. Skip exhausted buckets.
4. `dayNumber = calendarDaysBetween(2025-01-01, todayInConfiguredZone)`.
5. Return `deck[floorMod(dayNumber, deck.length)]`.

Each word occurs once per deck. Uneven collections stop contributing when exhausted, so strict alternation is possible only while all buckets have words. Repetition begins after the entire deck is exhausted. Missing a visit does not add unseen words to History.

Changing interests can repeat an encountered word. Adding, reordering, or deleting data changes the calendar. Version content and epoch together before promising a permanent production calendar. Theme, saved status, history, language, and route are not selection inputs.

Implementations: `lexi/selection.py` and `static/js/selection.js`. Tests compare selection across dates and interest combinations, and check leap days, dates before the epoch, and uneven buckets.

## API

| Endpoint | Response |
| --- | --- |
| `GET /api/catalog` | collections, words, site, timezone, today, epoch |
| `GET /api/daily` | Today's word for all collections, date, timezone |
| `GET /api/daily?collections=law,technology` | Today's word for the selected set |
| `GET /health` | HTTP 200 and `{"status":"ok"}` only when data and timezone validate |

Empty or unknown selections return HTTP 400. Invalid JSON, duplicate IDs, empty collections, missing required fields, or an invalid timezone return HTTP 503 with a clear error. Diagnostics remain in the server log. There is no public date-override API and no user-history upload. Data is reread per request.

## Persistence

`lexi:v1` stores version, theme, interests, saved, history, onboarded, and reduceMotion in browser localStorage. Each history item is `{id, date}`. A word is recorded once per viewing date; revisiting it on another day is another encounter. Onboarding previews do not count. Future-dated entries are excluded from History. References to deleted words are removed when loading the catalog.

LocalStorage does not sync between devices. If writing fails, the tab uses memory and reports that persistence is unavailable. Export downloads JSON for personal archival; an import UI is not implemented.

## Offline

The Service Worker caches the shell, local fonts, icons, and a valid online catalog after the first visit. Network is preferred, so online changes appear on refresh. Failed HTTP responses are surfaced rather than hidden by stale data. Without a network, the cached catalog supports the same browser-side selection for the current date. Cache cleanup only removes old LEXI caches. Some speech voices may require a network connection.

## Kotlin / Jetpack Glance

1. Read and validate the same JSON, preserving array order.
2. Use `LocalDate.now(ZoneId.of("Asia/Bishkek"))`, or the API's configured timezone.
3. Build the interleaved deck. Use `ChronoUnit.DAYS.between(epoch, day)` and `Math.floorMod`.
4. Display word, IPA, shortDefinition, and collection with Glance. Tap opens the native detail screen or `/#word/<id>`.
5. Request updates near the next date boundary using Android's supported scheduler, and refresh on app opening. Android may delay background work; exact-second widget refresh is not promised.
6. Native preferences do not automatically share browser localStorage. Cross-device accounts and synchronization need a later design.

Validate the web MVP on actual devices before starting the native app. A PWA home-screen icon is not a native widget.
