const express = require('express');
const { getQrData, createCheckin, getCheckinStatus, listEventCheckins, listMyCheckins } = require('../controllers/checkinController');
const authenticate = require('../middleware/authMiddleware');
const { optionalAuthenticate } = require('../middleware/authMiddleware');

const router = express.Router();

router.get('/events/:eventId/qr-data', authenticate, getQrData);
router.get('/events/:eventId/checkins', authenticate, listEventCheckins);
router.get('/mine', authenticate, listMyCheckins);
router.post('/', authenticate, createCheckin);
router.get('/status', optionalAuthenticate, getCheckinStatus);

module.exports = router;
