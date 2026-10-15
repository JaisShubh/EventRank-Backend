const jwt = require('jsonwebtoken');
const User = require('../models/User');

function createToken(userId) {
  return jwt.sign({ sub: userId }, process.env.JWT_SECRET, {
    expiresIn: process.env.JWT_EXPIRES_IN || '7d'
  });
}

function publicUser(user) {
  return { id: user.id, name: user.name, email: user.email };
}

async function register(req, res, next) {
  try {
    const { name, email, password } = req.body || {};
    if (typeof name !== 'string' || typeof email !== 'string' || typeof password !== 'string' || !name.trim() || !email.trim() || !password) {
      return res.status(400).json({ message: 'Name, email, and password are required' });
    }

    const normalizedEmail = email.trim().toLowerCase();
    const existingUser = await User.findOne({ email: normalizedEmail });
    if (existingUser) {
      return res.status(409).json({ message: 'An account with this email already exists' });
    }

    const user = await User.create({ name, email: normalizedEmail, password });
    return res.status(201).json({ user: publicUser(user), token: createToken(user.id) });
  } catch (error) {
    if (error.code === 11000) {
      return res.status(409).json({ message: 'An account with this email already exists' });
    }
    return next(error);
  }
}

async function login(req, res, next) {
  try {
    const { email, password } = req.body || {};
    if (typeof email !== 'string' || typeof password !== 'string' || !email.trim() || !password) {
      return res.status(400).json({ message: 'Email and password are required' });
    }

    const user = await User.findOne({ email: email.trim().toLowerCase() }).select('+password');
    if (!user || !(await user.comparePassword(password))) {
      return res.status(401).json({ message: 'Invalid email or password' });
    }

    return res.json({ user: publicUser(user), token: createToken(user.id) });
  } catch (error) {
    return next(error);
  }
}

async function getCurrentUser(req, res) {
  return res.json({ user: publicUser(req.user) });
}

module.exports = { register, login, getCurrentUser };
