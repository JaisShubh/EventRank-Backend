const GLOBAL_AVERAGE = 7;
const EVENT_PRIOR = 5;
const PREDICTION_PRIOR = 2;
const REVIEWER_TOLERANCE = 2;
const MIN_REVIEWER_WEIGHT = 0.1;
const MAX_ROUNDS = 20;

function scoreReviewSet(reviews) {
  const byEvent = new Map();
  for (const review of reviews) {
    const rating = Number(review.rating);
    const eventId = String(review.eventId || review.event_id || '');
    const userId = String(review.userId || review.user_id || '');
    if (!eventId || !userId || !Number.isFinite(rating)) continue;
    const item = { eventId, userId, rating: Math.max(1, Math.min(10, rating)) };
    if (!byEvent.has(eventId)) byEvent.set(eventId, []);
    byEvent.get(eventId).push(item);
  }

  const weights = new Map();
  for (const eventReviews of byEvent.values()) {
    for (const review of eventReviews) weights.set(review.userId, 1);
  }
  for (let round = 0; round < MAX_ROUNDS; round += 1) {
    const gaps = new Map();
    for (const eventReviews of byEvent.values()) {
      const totalWeight = eventReviews.reduce((sum, review) => sum + weights.get(review.userId), 0);
      const weightedTotal = eventReviews.reduce((sum, review) => sum + weights.get(review.userId) * review.rating, 0);
      for (const review of eventReviews) {
        const ownWeight = weights.get(review.userId);
        const otherWeight = totalWeight - ownWeight;
        if (otherWeight <= 0) continue;
        const crowdAverage = (weightedTotal - ownWeight * review.rating) / otherWeight;
        if (!gaps.has(review.userId)) gaps.set(review.userId, []);
        gaps.get(review.userId).push(Math.abs(review.rating - crowdAverage));
      }
    }
    if (!gaps.size) break;
    const nextWeights = new Map();
    for (const userId of weights.keys()) {
      const userGaps = gaps.get(userId);
      const averageGap = userGaps?.length ? userGaps.reduce((sum, value) => sum + value, 0) / userGaps.length : 0;
      nextWeights.set(userId, userGaps?.length
        ? Math.max(MIN_REVIEWER_WEIGHT, 1 / (1 + (averageGap / REVIEWER_TOLERANCE) ** 2))
        : 1);
    }
    const best = Math.max(...nextWeights.values());
    let change = 0;
    for (const [userId, weight] of nextWeights) {
      nextWeights.set(userId, weight / best);
      change = Math.max(change, Math.abs(nextWeights.get(userId) - weights.get(userId)));
    }
    weights.clear();
    for (const [userId, weight] of nextWeights) weights.set(userId, weight);
    if (change < 0.0001) break;
  }

  const scores = new Map();
  for (const [eventId, eventReviews] of byEvent) {
    const weightedSum = eventReviews.reduce((sum, review) => sum + review.rating * weights.get(review.userId), 0);
    const totalWeight = eventReviews.reduce((sum, review) => sum + weights.get(review.userId), 0);
    scores.set(eventId, Number(((weightedSum + EVENT_PRIOR * GLOBAL_AVERAGE) / (totalWeight + EVENT_PRIOR)).toFixed(1)));
  }
  return { scores, weights };
}

function predictScore(event, reviewedEvents) {
  let totalWeight = 0;
  let weightedScore = 0;
  for (const other of reviewedEvents) {
    let weight = 0;
    if (event.organizer && other.organizer === event.organizer) weight += 2;
    if (event.category && other.category === event.category) weight += 1;
    totalWeight += weight;
    weightedScore += weight * other.score;
  }
  return Number(((weightedScore + PREDICTION_PRIOR * GLOBAL_AVERAGE) / (totalWeight + PREDICTION_PRIOR)).toFixed(1));
}

function compositeRank(event, averageRating, reviewCount, turnoutCount, now = Date.now()) {
  const bayesianRating = ((5 * GLOBAL_AVERAGE) + reviewCount * (averageRating || GLOBAL_AVERAGE)) / (5 + reviewCount);
  const ratingScore = (bayesianRating / 10) * 100;
  const turnoutScore = event.capacity > 0 ? (Math.min(turnoutCount / event.capacity, 1.2) / 1.2) * 100 : 50;
  const organizerScore = 70;
  const baseScore = ratingScore * 0.5 + turnoutScore * 0.3 + organizerScore * 0.2;
  const daysUntil = event.startTime ? (new Date(event.startTime).getTime() - now) / 86400000 : 0;
  const recency = daysUntil >= 0 ? 1 + 0.05 * Math.exp(-daysUntil / 7) : Math.exp(-Math.abs(daysUntil) / 30);
  return Number(Math.max(0, Math.min(100, baseScore * recency)).toFixed(1));
}

function enrichEvents(events, reviews, checkins) {
  const plainEvents = events.map((event) => event.toObject ? event.toObject() : { ...event });
  const { scores } = scoreReviewSet(reviews);
  const reviewGroups = new Map();
  for (const review of reviews) {
    const id = String(review.eventId || review.event_id || '');
    if (!reviewGroups.has(id)) reviewGroups.set(id, []);
    reviewGroups.get(id).push(Number(review.rating));
  }
  const turnout = new Map();
  for (const checkin of checkins) {
    const id = String(checkin.eventId || checkin.event_id || '');
    turnout.set(id, (turnout.get(id) || 0) + 1);
  }

  const scored = plainEvents.map((event) => {
    const id = String(event._id || event.id);
    const ratings = reviewGroups.get(id) || [];
    const averageRating = ratings.length ? Number((ratings.reduce((sum, value) => sum + value, 0) / ratings.length).toFixed(2)) : null;
    const turnoutCount = turnout.get(id) || 0;
    const score = scores.get(id) ?? null;
    return {
      ...event,
      id,
      organizer_id: String(event.organizerId),
      start_time: event.startTime,
      lat: event.location?.lat ?? null,
      lng: event.location?.lng ?? null,
      review_count: ratings.length,
      turnout_count: turnoutCount,
      avg_rating: averageRating,
      score,
      is_predicted: score === null
    };
  });
  const reviewedEvents = scored.filter((event) => event.score !== null);
  for (const event of scored) {
    if (event.score === null) event.score = predictScore(event, reviewedEvents);
    event.composite_score = compositeRank(event, event.avg_rating, event.review_count, event.turnout_count);
  }
  return scored;
}

module.exports = { scoreReviewSet, enrichEvents, compositeRank };
