const mongoose = require('mongoose');
const Event = require('../models/Event');
const Participation = require('../models/Participation');

async function getParticipationStatus(req, res, next) {
  try {
    if (!mongoose.isValidObjectId(req.params.eventId)) {
      return res.status(400).json({ message: 'Invalid event id' });
    }
    const event = await Event.findById(req.params.eventId).select('capacity registeredCount');
    if (!event) return res.status(404).json({ message: 'Event not found' });
    const participation = await Participation.findOne({ eventId: event._id, userId: req.user._id });
    return res.json({
      participating: Boolean(participation),
      canParticipate: req.user.role === 'participant',
      participation,
      registered_count: event.registeredCount || 0,
      capacity: event.capacity
    });
  } catch (error) {
    return next(error);
  }
}

async function joinEvent(req, res, next) {
  let reservedSeat = false;
  let event;
  try {
    if (req.user.role !== 'participant') {
      return res.status(403).json({ message: 'Only participant accounts can join events' });
    }
    if (!mongoose.isValidObjectId(req.params.eventId)) {
      return res.status(400).json({ message: 'Invalid event id' });
    }

    event = await Event.findById(req.params.eventId);
    if (!event) return res.status(404).json({ message: 'Event not found' });
    if (event.startTime.getTime() <= Date.now()) {
      return res.status(400).json({ message: 'Registration for this event has closed' });
    }

    const filter = { eventId: event._id, userId: req.user._id };
    const existing = await Participation.findOne(filter);
    if (existing) {
      return res.json({ message: 'You are already participating in this event', participating: true, already_participating: true, participation: existing });
    }

    const reservation = await Event.updateOne(
      { _id: event._id, $or: [{ registeredCount: { $lt: event.capacity } }, { registeredCount: { $exists: false } }] },
      { $inc: { registeredCount: 1 } }
    );
    if (!reservation.modifiedCount) {
      return res.status(409).json({ message: 'This event has reached its participant capacity' });
    }
    reservedSeat = true;

    const participation = await Participation.create(filter);
    return res.status(201).json({ message: 'You are participating in this event', participating: true, participation });
  } catch (error) {
    if (reservedSeat && event) {
      await Event.updateOne({ _id: event._id }, { $inc: { registeredCount: -1 } }).catch(() => {});
    }
    if (error.code === 11000) {
      const participation = await Participation.findOne({ eventId: event._id, userId: req.user._id });
      return res.json({ message: 'You are already participating in this event', participating: true, already_participating: true, participation });
    }
    return next(error);
  }
}

async function listMyParticipations(req, res, next) {
  try {
    const participations = await Participation.find({ userId: req.user._id })
      .sort({ createdAt: -1 })
      .populate('eventId', 'title category organizer venue startTime capacity registeredCount');
    return res.json({ participations: participations.filter((item) => item.eventId) });
  } catch (error) {
    return next(error);
  }
}

module.exports = { getParticipationStatus, joinEvent, listMyParticipations };
