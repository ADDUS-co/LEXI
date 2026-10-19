// Recall is a learning aid. Vocabulary remains public data, not a security secret.
export function answerMatches(answer, word) {
  const normalize = value => String(value).normalize('NFKC').trim().replace(/\s+/g,' ').toLocaleLowerCase('en');
  return normalize(answer) === normalize(word) && normalize(word).length > 0;
}

export function withoutAnswer(text, word) {
  const escaped = String(word).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  return String(text).replace(new RegExp(escaped,'giu'),'_____');
}
