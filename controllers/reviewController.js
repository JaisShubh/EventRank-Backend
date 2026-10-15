const mongoose = require('mongoose');
const Checkin = require('../models/Checkin');
const Event = require('../models/Event');
const Review = require('../models/Review');
const Participation = require('../models/Participation');
const { analyzeSentiment, isSpamReview, generateProsAndCons } = require('../services/reviewAnalysis');
const { scoreReviewSet, compositeRank } = require('../services/eventRanking');

function serializeReview(review, verifiedAttendee = false) {
  const data = review.toObject ? review.toObject() : review;
  return {
    ...data,
    id: String(data._id || data.id),
    event_id: String(data.eventId),
    user_id: String(data.userId),
    verified_attendee: verifiedAttendee
  };
}

async function getEventReviews(req, res, next) {
  try {
    if (!mongoose.isValidObjectId(req.params.eventId)) return res.status(400).json({ message: 'Invalid event id' });
    const event = await Event.findById(req.params.eventId).select('_id');
    if (!event) return res.status(404).json({ message: 'Event not found' });
    const [reviews, checkins] = await Promise.all([
      Review.find({ eventId: event._id }).sort({ createdAt: -1 }),
      Checkin.find({ eventId: event._id }).select('userId')
    ]);
    const verifiedUsers = new Set(checkins.map((item) => String(item.userId)));
    const items = reviews.map((review) => ({
      ...serializeReview(review, verifiedUsers.has(String(review.userId))),
      sentiment: review.comment ? analyzeSentiment(review.comment) : null
    }));
    return res.json({ reviews: items, count: items.length });
  } catch (error) {
    return next(error);
  }
}

async function createOrUpdateReview(req, res, next) {
  try {
    if (!mongoose.isValidObjectId(req.params.eventId)) return res.status(400).json({ message: 'Invalid event id' });
    const rating = Number(req.body?.rating);
    if (!Number.isFinite(rating) || rating < 1 || rating > 10) {
      return res.status(400).json({ message: 'Rating must be a number between 1 and 10' });
    }
    const comment = String(req.body?.comment || '').trim();
    if (comment.length > 5000) return res.status(400).json({ message: 'Comment must be 5000 characters or fewer' });
    if (comment && isSpamReview(comment)) return res.status(400).json({ message: 'Review rejected: comment appears to be spam or too short' });

    const event = await Event.findById(req.params.eventId).select('_id startTime');
    if (!event) return res.status(404).json({ message: 'Event not found' });
    if (req.user.role !== 'participant') {
      return res.status(403).json({ message: 'Only participant accounts can review events' });
    }
    if (event.startTime.getTime() > Date.now()) {
      return res.status(403).json({ message: 'Reviews are available after the event has ended' });
    }
    const participation = await Participation.exists({ eventId: event._id, userId: req.user._id });
    if (!participation) {
      return res.status(403).json({ message: 'You must participate in this event before submitting a review' });
    }
    const filter = { eventId: event._id, userId: req.user._id };
    const existing = await Review.findOne(filter);
    const review = await Review.findOneAndUpdate(
      filter,
      { $set: { rating, comment }, $setOnInsert: filter },
      { new: true, upsert: true, runValidators: true }
    );
    const verifiedAttendee = Boolean(await Checkin.exists(filter));
    return res.status(existing ? 200 : 201).json({
      message: existing ? 'Review updated successfully' : 'Review submitted successfully',
      review: serializeReview(review, verifiedAttendee),
      verified_attendee: verifiedAttendee
    });
  } catch (error) {
    return next(error);
  }
}

async function deleteReview(req, res, next) {
  try {
    if (!mongoose.isValidObjectId(req.params.reviewId)) return res.status(400).json({ message: 'Invalid review id' });
    const review = await Review.findById(req.params.reviewId);
    if (!review) return res.status(404).json({ message: 'Review not found' });
    if (req.params.eventId && !review.eventId.equals(req.params.eventId)) return res.status(404).json({ message: 'Review not found' });
    if (!review.userId.equals(req.user._id)) return res.status(403).json({ message: 'You are not authorized to delete this review' });
    await review.deleteOne();
    return res.json({ message: 'Review deleted successfully' });
  } catch (error) {
    return next(error);
  }
}

async function eventInsights(req, res, next) {
  try {
    if (!mongoose.isValidObjectId(req.params.eventId)) return res.status(400).json({ message: 'Invalid event id' });
    const event = await Event.findById(req.params.eventId);
    if (!event) return res.status(404).json({ message: 'Event not found' });
    const [reviews, verifiedAttendees] = await Promise.all([
      Review.find({ eventId: event._id }).select('eventId userId rating comment').lean(),
      Checkin.countDocuments({ eventId: event._id })
    ]);
    const averageRating = reviews.length
      ? Number((reviews.reduce((sum, item) => sum + item.rating, 0) / reviews.length).toFixed(2))
      : 0;
    const { scores } = scoreReviewSet(reviews);
    const credibilityScore = scores.get(String(event._id)) ?? null;
    const compositeScore = compositeRank(event, averageRating, reviews.length, verifiedAttendees);
    const comments = reviews.map((item) => item.comment).filter(Boolean);
    const sentimentScores = comments.map((comment) => analyzeSentiment(comment));
    const sentimentCounts = { positive: 0, neutral: 0, negative: 0 };
    for (const sentiment of sentimentScores) sentimentCounts[sentiment.label] += 1;
    return res.json({
      event_id: String(event._id),
      title: event.title,
      total_reviews: reviews.length,
      verified_attendees: verifiedAttendees,
      average_rating: averageRating,
      credibility_score: credibilityScore,
      composite_rank: compositeScore,
      sentiment_overview: {
        average_compound: sentimentScores.length
          ? Number((sentimentScores.reduce((sum, item) => sum + item.compound, 0) / sentimentScores.length).toFixed(3))
          : 0,
        counts: sentimentCounts
      },
      pros_and_cons: generateProsAndCons(comments)
    });
  } catch (error) {
    return next(error);
  }
}

async function globalInsights(req, res, next) {
  try {
    const [totalEvents, reviews, totalCheckins] = await Promise.all([
      Event.countDocuments(),
      Review.find({}).select('rating comment').lean(),
      Checkin.countDocuments()
    ]);
    const ratings = reviews.map((item) => Number(item.rating)).filter(Number.isFinite);
    const comments = reviews.map((item) => item.comment).filter(Boolean).slice(0, 30);
    return res.json({
      total_events: totalEvents,
      total_reviews: reviews.length,
      total_checkins: totalCheckins,
      campus_average_rating: ratings.length
        ? Number((ratings.reduce((sum, rating) => sum + rating, 0) / ratings.length).toFixed(2))
        : 0,
      pros_and_cons: generateProsAndCons(comments)
    });
  } catch (error) {
    return next(error);
  }
}

module.exports = { getEventReviews, createOrUpdateReview, deleteReview, eventInsights, globalInsights };
