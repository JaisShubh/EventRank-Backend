const jwt = require('jsonwebtoken');
const User = require('../models/User');

function createToken(userId) {
  return jwt.sign({ sub: userId }, process.env.JWT_SECRET, {
    expiresIn: process.env.JWT_EXPIRES_IN || '7d'
  });
}

function publicUser(user) {
  return { id: user.id, name: user.name, email: user.email, role: user.role || 'participant' };
}

async function register(req, res, next) {
  try {
    const { name, email, password } = req.body || {};
    const role = req.body?.role || 'participant';
    if (typeof name !== 'string' || typeof email !== 'string' || typeof password !== 'string' || !name.trim() || !email.trim() || !password) {
      return res.status(400).json({ message: 'Name, email, and password are required' });
    }
    if (name.trim().length < 2 || name.trim().length > 80 || email.trim().length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      return res.status(400).json({ message: 'Enter a valid name and email address' });
    }
    if (password.length < 8 || Buffer.byteLength(password, 'utf8') > 72) {
      return res.status(400).json({ message: 'Password must be 8 or more characters and no more than 72 UTF-8 bytes' });
    }
    if (!['community', 'participant'].includes(role)) {
      return res.status(400).json({ message: 'Role must be community or participant' });
    }

    const normalizedEmail = email.trim().toLowerCase();
    const existingUser = await User.findOne({ email: normalizedEmail });
    if (existingUser) {
      return res.status(409).json({ message: 'An account with this email already exists' });
    }

    const user = await User.create({ name, email: normalizedEmail, password, role });
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
    if (email.trim().length > 254 || Buffer.byteLength(password, 'utf8') > 72) {
      return res.status(400).json({ message: 'Invalid email or password length' });
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
