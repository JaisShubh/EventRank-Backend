const POSITIVE = new Set(('amazing awesome beautiful best brilliant calm clean comfortable delicious easy excellent exciting fantastic favorite fun friendly good great happy helpful incredible love lovely nice perfect pleasant quick recommend relaxing reliable smooth tasty wonderful worth').split(' '));
const NEGATIVE = new Set(('awful bad boring broken crowded difficult disappointing dirty expensive fail hate horrible late loud messy poor rude slow terrible uncomfortable unhelpful unpleasant worst').split(' '));
const SPAM_TERMS = ['click here', 'free money', 'whatsapp', 'buy now', 'telegram', 'crypto', 'http://', 'https://'];
const NEGATORS = new Set(['not', 'never', 'no', "don't", 'didnt', "didn't", 'isnt', "isn't", 'wasnt', "wasn't"]);

function analyzeSentiment(text) {
  const value = String(text || '').trim();
  if (!value) return { compound: 0, pos: 0, neu: 1, neg: 0, label: 'neutral' };
  const tokens = value.toLowerCase().match(/[a-z']+/g) || [];
  let positive = 0;
  let negative = 0;
  let raw = 0;
  for (let i = 0; i < tokens.length; i += 1) {
    let score = POSITIVE.has(tokens[i]) ? 1 : NEGATIVE.has(tokens[i]) ? -1 : 0;
    if (!score) continue;
    if (tokens.slice(Math.max(0, i - 3), i).some((word) => NEGATORS.has(word))) score *= -1;
    if (tokens[i - 1] === 'very' || tokens[i - 1] === 'really' || tokens[i - 1] === 'extremely') score *= 1.5;
    raw += score;
    if (score > 0) positive += score;
    else negative += Math.abs(score);
  }
  const compound = raw / Math.sqrt(raw * raw + 15);
  const wordTotal = positive + negative;
  const pos = wordTotal ? positive / wordTotal : 0;
  const neg = wordTotal ? negative / wordTotal : 0;
  const neu = wordTotal ? 0 : 1;
  return {
    compound: Number(compound.toFixed(3)),
    pos: Number(pos.toFixed(3)),
    neu: Number(neu.toFixed(3)),
    neg: Number(neg.toFixed(3)),
    label: compound >= 0.05 ? 'positive' : compound <= -0.05 ? 'negative' : 'neutral'
  };
}

function isSpamReview(text) {
  const value = String(text || '').trim().toLowerCase();
  return value.length < 5 || SPAM_TERMS.some((term) => value.includes(term)) || /(.)\1{4,}/u.test(value);
}

function generateProsAndCons(reviews) {
  const pros = [];
  const cons = [];
  for (const review of reviews) {
    if (!review || isSpamReview(review)) continue;
    for (const sentence of String(review).split(/[.!?]+/).map((part) => part.trim()).filter((part) => part.length > 10)) {
      const { compound } = analyzeSentiment(sentence);
      const destination = compound >= 0.25 ? pros : compound <= -0.25 ? cons : null;
      if (destination && !destination.includes(sentence) && destination.length < 4) destination.push(sentence);
    }
  }
  return {
    pros: pros.length ? pros : ['Good overall experience'],
    cons: cons.length ? cons : ['No major complaints reported']
  };
}

module.exports = { analyzeSentiment, isSpamReview, generateProsAndCons };
