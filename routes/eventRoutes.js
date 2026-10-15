const express = require('express');
const {
  listEvents,
  listCategories,
  recommendations,
  getEvent,
  createEvent,
  updateEvent,
  deleteEvent
} = require('../controllers/eventController');
const authenticate = require('../middleware/authMiddleware');
const { getQrData, listEventCheckins } = require('../controllers/checkinController');

const router = express.Router();

router.get('/categories', listCategories);
router.get('/recommendations', recommendations);
router.get('/:eventId/qr-data', authenticate, getQrData);
router.get('/:eventId/checkins', authenticate, listEventCheckins);
router.get('/', listEvents);
router.get('/:eventId', getEvent);
router.post('/', authenticate, createEvent);
router.put('/:eventId', authenticate, updateEvent);
router.delete('/:eventId', authenticate, deleteEvent);

module.exports = router;
