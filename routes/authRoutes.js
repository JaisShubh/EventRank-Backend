const express = require('express');
const { register, login, getCurrentUser } = require('../controllers/authController');
const authenticate = require('../middleware/authMiddleware');

const router = express.Router();

router.post('/register', register);
router.post('/signup', register);
router.post('/login', login);
router.get('/me', authenticate, getCurrentUser);

module.exports = router;
