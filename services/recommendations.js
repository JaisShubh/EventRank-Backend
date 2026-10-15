const STOP_WORDS = new Set(('a an and are as at be by for from has have he in is it its of on or that the their this to was were will with you your').split(' '));

function tokenize(value) {
  return String(value || '').toLowerCase().match(/[\p{L}\p{N}]+/gu)?.filter((word) => word.length > 1 && !STOP_WORDS.has(word)) || [];
}

function recommendEvents(interests, events, topN = 5) {
  const count = Math.max(0, Math.min(100, Number.parseInt(topN, 10) || 5));
  if (!events.length) return [];
  if (!interests.length) return events.slice(0, count).map((event) => ({ ...event, match_score: 0 }));

  const docs = events.map((event) => tokenize(`${event.title || ''} ${event.category || ''} ${event.description || ''}`));
  const query = tokenize(interests.join(' '));
  const terms = new Set([...query, ...docs.flat()]);
  const idf = new Map();
  for (const term of terms) {
    const documentFrequency = docs.filter((doc) => doc.includes(term)).length;
    idf.set(term, Math.log((1 + docs.length) / (1 + documentFrequency)) + 1);
  }
  const vector = (tokens) => {
    const counts = new Map();
    for (const token of tokens) counts.set(token, (counts.get(token) || 0) + 1);
    return new Map([...counts].map(([term, frequency]) => [term, (1 + Math.log(frequency)) * idf.get(term)]));
  };
  const queryVector = vector(query);
  const magnitude = (v) => Math.sqrt([...v.values()].reduce((sum, value) => sum + value * value, 0));
  const queryMagnitude = magnitude(queryVector);
  return events.map((event, index) => {
    const docVector = vector(docs[index]);
    let dot = 0;
    for (const [term, value] of queryVector) dot += value * (docVector.get(term) || 0);
    const denominator = queryMagnitude * magnitude(docVector);
    return { ...event, match_score: denominator ? Number((dot / denominator).toFixed(3)) : 0 };
  }).sort((a, b) => b.match_score - a.match_score).slice(0, count);
}

module.exports = { recommendEvents };
