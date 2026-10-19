# Daily selection contract / Android preparation

The deck algorithm remains version 1. Scheduling and local recall state are version 2 additions. This is not an Android app.

## Inputs

- Ordered collection metadata with unique stable IDs in `collections.json`.
- Ordered word entries with unique IDs and valid collection references in `words.json`.
- A nonempty set of selected collection IDs. Selection-click order and duplicates do not affect the result.
- A learning date determined from the device IANA timezone and chosen HH:MM update time. Before that local boundary, use the preceding calendar date. Device clocks must be accurate for offline use.
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
| `GET /api/daily?collections=law,technology&timezone=Europe/London&update_time=08:00` | Word for the specified local schedule, learning date, calendarDate, updateTime, timezone, nextUpdateAt |
| `GET /health` | HTTP 200 and `{"status":"ok"}` only when data and timezone validate |

The API defaults to server timezone Asia/Bishkek and 00:00 for compatibility. It cannot read browser preferences: native clients must send timezone and update_time. The web app calculates locally using the same rules.

Empty or unknown selections, invalid update times, and unknown timezone query parameters return HTTP 400. Invalid JSON, duplicate IDs, empty collections, missing required fields, or an invalid timezone return HTTP 503 with a clear error. Diagnostics remain in the server log. There is no public date-override API and no user-history upload. Data is reread per request.

## Persistence

`lexi:v1` remains the storage key to preserve existing data. Schema version 2 stores version, theme, interests, saved, history, onboarded, reduceMotion, updateTime, and hiddenWords. Legacy onboarded users default to 00:00; new users default to 08:00. The timezone follows the device and is not frozen in storage. Each history item is `{id, date}`, using the real local viewing date rather than the learning date. A word is recorded once per viewing date; revisiting it on another day is another encounter. Onboarding previews do not count. Future-dated entries are excluded from History. References to deleted words are removed when loading the catalog.

LocalStorage does not sync between devices. If writing fails, the tab uses memory and reports that persistence is unavailable. Export downloads JSON for personal archival; an import UI is not implemented.

## Offline

The Service Worker caches the shell, local fonts, icons, and a valid online catalog after the first visit. Network is preferred, so online changes appear on refresh. Failed HTTP responses are surfaced rather than hidden by stale data. Without a network, the cached catalog supports the same browser-side selection for the current date. Cache cleanup only removes old LEXI caches. Some speech voices may require a network connection.

## Kotlin / Jetpack Glance

1. Read and validate the same JSON, preserving array order.
2. Read the device zone (`ZoneId.systemDefault()`) and the chosen HH:MM. Resolve today’s local rollover and use the preceding learning date until that boundary. Android's ZoneRules provides valid offsets: choose the earliest instant for an overlap, or the transition's first valid local minute for a gap.
3. Build the interleaved deck. Use `ChronoUnit.DAYS.between(epoch, day)` and `Math.floorMod`.
4. Display word, IPA, shortDefinition, and collection with Glance. Tap opens the native detail screen or `/#word/<id>`.
5. Request updates near the next date boundary using Android's supported scheduler, and refresh on app opening. Android may delay background work; exact-second widget refresh is not promised.
6. Native preferences do not automatically share browser localStorage. Cross-device accounts and synchronization need a later design.

Validate the web MVP on actual devices before starting the native app. A PWA home-screen icon is not a native widget.


## Local scheduling and daylight-saving rules

Python: `lexi/schedule.py`; browser: `static/js/schedule.js`. A rollover is a local wall-clock boundary, not “the previous timestamp plus 24 hours”. For a repeated clock time choose its earliest occurrence; after that first boundary the learning day must not revert during the repeated hour. For a nonexistent clock time use the first valid minute after the gap. Half-hour transitions and quarter-hour offsets are covered by tests.

The open page checks every 30 seconds and on visibility restoration. A closed browser does not run a background scheduler; the next visit calculates the current learning date immediately. No notifications are promised. Changing the update time can recalculate the current word. Theme changes do not.

## Memory cards

`hiddenWords` contains stable word IDs. Double-click on desktop or two nearby touch taps (within 380 ms and 30 CSS pixels) flips a word. An accessible Test my memory button also hides it. Persist state before starting the visual transition so closing the browser during the animation cannot lose the flip.

The back offers a definition with exact occurrences of the answer removed. It omits IPA, pronunciation, share, examples, full explanations, and source links. Titles and normal Saved/History labels also mask a hidden answer. A full answer matches case-insensitively after Unicode NFKC normalization, trimming, and whitespace normalization; partial or incorrect text does not reveal it. A second double-tap is the alternative. Keyboard users can activate Press twice to reveal twice within 1.8 seconds.

After a reveal the word stays visible until hidden again. State is per word, so returning to an older card preserves its side. Deleted IDs are removed on catalog load. This is an optional recall aid, not access control: the public catalog still contains all vocabulary.
