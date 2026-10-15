const mongoose = require('mongoose');

const participationSchema = new mongoose.Schema(
  {
    eventId: { type: mongoose.Schema.Types.ObjectId, ref: 'Event', required: true, index: true },
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, index: true }
  },
  { timestamps: true }
);

participationSchema.index({ eventId: 1, userId: 1 }, { unique: true });

module.exports = mongoose.model('Participation', participationSchema);
