// Portable daily-word rules. Keep in sync with lexi/selection.py.
export const EPOCH = '2025-01-01';

export function dateInTimezone(timezone, now = new Date()) {
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const part = name => parts.find(item => item.type === name).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

export function buildDeck(collections, words, selectedIds) {
  const selected = new Set(selectedIds);
  if (!selected.size || [...selected].some(id => !collections.some(c => c.id === id))) {
    throw new Error('Select at least one valid collection.');
  }
  const buckets = collections.filter(c => selected.has(c.id))
    .map(c => words.filter(word => word.collectionId === c.id));
  if (buckets.some(bucket => !bucket.length)) throw new Error('A selected collection has no words.');
  const deck = [];
  for (let index = 0; index < Math.max(...buckets.map(bucket => bucket.length)); index++) {
    for (const bucket of buckets) if (bucket[index]) deck.push(bucket[index]);
  }
  return deck;
}

export function selectWord(collections, words, selectedIds, day) {
  const deck = buildDeck(collections, words, selectedIds);
  const dayNumber = Math.round((Date.parse(`${day}T00:00:00Z`) - Date.parse(`${EPOCH}T00:00:00Z`)) / 86400000);
  if (!Number.isFinite(dayNumber)) throw new Error('The calendar date is invalid.');
  return deck[((dayNumber % deck.length) + deck.length) % deck.length];
}

