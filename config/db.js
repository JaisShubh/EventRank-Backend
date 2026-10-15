const mongoose = require('mongoose');
let connectionPromise;

async function connectDB() {
  const { MONGODB_URI } = process.env;
  if (!MONGODB_URI) {
    throw new Error('MONGODB_URI is not configured');
  }

  if (mongoose.connection.readyState === 1) return mongoose.connection;
  if (!connectionPromise) {
    connectionPromise = mongoose.connect(MONGODB_URI)
      .then(() => {
        console.log('MongoDB connected');
        return mongoose.connection;
      })
      .catch((error) => {
        connectionPromise = null;
        throw error;
      });
  }
  return connectionPromise;
}

module.exports = connectDB;
