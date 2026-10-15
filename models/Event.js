const mongoose = require('mongoose');

const eventSchema = new mongoose.Schema(
  {
    title: { type: String, required: true, trim: true, minlength: 2, maxlength: 160 },
    description: { type: String, trim: true, maxlength: 10000, default: '' },
    category: { type: String, trim: true, maxlength: 80, default: 'General', index: true },
    organizer: { type: String, trim: true, maxlength: 120, required: true },
    organizerId: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true, index: true },
    venue: { type: String, trim: true, maxlength: 240, required: true },
    location: {
      lat: { type: Number, min: -90, max: 90, default: null },
      lng: { type: Number, min: -180, max: 180, default: null }
    },
    startTime: { type: Date, required: true, index: true },
    capacity: { type: Number, min: 1, max: 1000000, default: 100 }
  },
  { timestamps: true }
);

eventSchema.index({ title: 'text', description: 'text', venue: 'text', organizer: 'text' });

module.exports = mongoose.model('Event', eventSchema);
