const mongoose = require('mongoose');

const checkinSchema = new mongoose.Schema(
  {
    eventId: { type: mongoose.Schema.Types.ObjectId, ref: 'Event', required: true, index: true },
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, index: true },
    verified: { type: Boolean, default: true }
  },
  { timestamps: true }
);

checkinSchema.index({ eventId: 1, userId: 1 }, { unique: true });

module.exports = mongoose.model('Checkin', checkinSchema);
