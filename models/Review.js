const mongoose = require('mongoose');

const reviewSchema = new mongoose.Schema(
  {
    eventId: { type: mongoose.Schema.Types.ObjectId, ref: 'Event', required: true, index: true },
    userId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, index: true },
    rating: { type: Number, required: true, min: 1, max: 10 },
    comment: { type: String, trim: true, maxlength: 5000, default: '' }
  },
  { timestamps: true }
);

reviewSchema.index({ eventId: 1, userId: 1 }, { unique: true });

module.exports = mongoose.model('Review', reviewSchema);
