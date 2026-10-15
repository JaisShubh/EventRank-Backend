const express = require('express');
const { getEventReviews, createOrUpdateReview, deleteReview, eventInsights, globalInsights } = require('../controllers/reviewController');
const authenticate = require('../middleware/authMiddleware');

const router = express.Router();

router.get('/events/:eventId/reviews', getEventReviews);
router.post('/events/:eventId/reviews', authenticate, createOrUpdateReview);
router.get('/events/:eventId/insights', eventInsights);
router.get('/insights', globalInsights);
router.delete('/events/:eventId/reviews/:reviewId', authenticate, deleteReview);
router.delete('/reviews/:reviewId', authenticate, deleteReview);

module.exports = router;
