require('dotenv').config();

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const connectDB = require('./config/db');
const authRoutes = require('./routes/authRoutes');
const eventRoutes = require('./routes/eventRoutes');
const reviewRoutes = require('./routes/reviewRoutes');
const checkinRoutes = require('./routes/checkinRoutes');
const { createCheckin, getCheckinStatus } = require('./controllers/checkinController');
const authenticate = require('./middleware/authMiddleware');
const { optionalAuthenticate } = require('./middleware/authMiddleware');

const app = express();
const port = Number(process.env.PORT) || 5000;

if (!process.env.JWT_SECRET || process.env.JWT_SECRET.length < 32 || process.env.JWT_SECRET === 'replace-this-with-a-long-random-secret') {
  throw new Error('Set JWT_SECRET in .env to a random value of at least 32 characters before starting the server');
}
if (!process.env.QR_SECRET || process.env.QR_SECRET.length < 32 || process.env.QR_SECRET === 'replace-with-a-different-long-random-secret') {
  throw new Error('Set QR_SECRET in .env to a separate random value of at least 32 characters before starting the server');
}

const allowedOrigins = new Set(
  (process.env.CORS_ORIGINS || 'http://localhost:5173,http://127.0.0.1:5173')
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean)
);

app.use(helmet());
app.use(cors({
  origin(origin, callback) {
    // Requests from server-side clients such as Postman do not send an Origin.
    if (!origin || allowedOrigins.has(origin)) return callback(null, true);
    return callback(new Error('Origin is not allowed by CORS'));
  }
}));
app.use(express.json({ limit: '10kb' }));

app.get('/api/health', (req, res) => res.json({ status: 'ok' }));
app.use('/api/auth', authRoutes);
app.use('/api/events', eventRoutes);
app.use('/api', reviewRoutes);
app.use('/api/checkins', checkinRoutes);
app.post('/api/checkin', authenticate, createCheckin);
app.get('/api/checkin/status', optionalAuthenticate, getCheckinStatus);

app.use((req, res) => res.status(404).json({ message: 'Route not found' }));
app.use((error, req, res, next) => {
  if (res.headersSent) return next(error);
  if (error.name === 'ValidationError' || error.name === 'CastError' || error.type === 'entity.parse.failed') {
    return res.status(400).json({ message: error.message || 'Invalid request body' });
  }
  if (error.code === 11000) {
    return res.status(409).json({ message: 'A record with those details already exists' });
  }
  if (error.message === 'Origin is not allowed by CORS') {
    return res.status(403).json({ message: 'Origin is not allowed' });
  }
  console.error(error);
  return res.status(500).json({ message: 'Internal server error' });
});

async function start() {
  try {
    await connectDB();
    app.listen(port, () => console.log(`EventRank API listening on port ${port}`));
  } catch (error) {
    console.error('Failed to start server:', error.message);
    process.exit(1);
  }
}

if (require.main === module) start();

module.exports = app;
