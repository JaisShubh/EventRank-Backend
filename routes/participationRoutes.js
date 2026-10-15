const express = require('express');
const { listMyParticipations } = require('../controllers/participationController');
const authenticate = require('../middleware/authMiddleware');

const router = express.Router();

router.get('/mine', authenticate, listMyParticipations);

module.exports = router;
