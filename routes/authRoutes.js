const express = require('express');
const { register, login, getCurrentUser } = require('../controllers/authController');
const authenticate = require('../middleware/authMiddleware');
const { rateLimit } = require('express-rate-limit');

const router = express.Router();
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 10,
  standardHeaders: 'draft-8',
  legacyHeaders: false,
  message: { message: 'Too many authentication attempts. Please try again in 15 minutes.' }
});

router.post('/register', authLimiter, register);
router.post('/signup', authLimiter, register);
router.post('/login', authLimiter, login);
router.get('/me', authenticate, getCurrentUser);

module.exports = router;
