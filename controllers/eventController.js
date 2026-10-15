const mongoose = require('mongoose');
const Event = require('../models/Event');
const Review = require('../models/Review');
const Checkin = require('../models/Checkin');
const { enrichEvents } = require('../services/eventRanking');
const { recommendEvents } = require('../services/recommendations');

const editableFields = ['title', 'description', 'category', 'venue', 'startTime', 'capacity'];

function eventPayload(body = {}, { creating = false } = {}) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) body = {};
  const payload = {};
  for (const field of editableFields) {
    const legacyField = field === 'startTime' ? 'start_time' : field;
    if (Object.prototype.hasOwnProperty.call(body, field)) payload[field] = body[field];
    else if (Object.prototype.hasOwnProperty.call(body, legacyField)) payload[field] = body[legacyField];
  }

  if (Object.prototype.hasOwnProperty.call(body, 'location')) {
    payload.location = body.location;
  } else if ('lat' in body || 'lng' in body) {
    payload.location = {};
    if ('lat' in body) payload.location.lat = body.lat;
    if ('lng' in body) payload.location.lng = body.lng;
  }

  if (creating) {
    payload.organizer = String(body.organizer || '').trim() || undefined;
  } else if (Object.prototype.hasOwnProperty.call(body, 'organizer')) {
    payload.organizer = String(body.organizer || '').trim();
  }

  return payload;
}

function serializeEvent(event) {
  const data = event.toObject ? event.toObject() : event;
  return {
    ...data,
    id: String(data._id || data.id),
    organizer_id: String(data.organizerId),
    start_time: data.startTime,
    lat: data.location?.lat ?? null,
    lng: data.location?.lng ?? null
  };
}

function parseCoordinates(location) {
  if (!location || typeof location !== 'object' || Array.isArray(location)) return location;
  const parsed = {};
  for (const key of ['lat', 'lng']) {
    if (location[key] === null) parsed[key] = null;
    else if (location[key] !== undefined && location[key] !== '') parsed[key] = Number(location[key]);
  }
  return parsed;
}

async function listEvents(req, res, next) {
  try {
    const scoredEvents = await getScoredEvents();
    const search = String(req.query.search || req.query.q || '').trim();
    const category = String(req.query.category || '').trim();
    const organizer = String(req.query.organizer || '').trim();
    let filtered = scoredEvents.filter((event) => {
      if (category && category.toLowerCase() !== 'all' && event.category.toLowerCase() !== category.toLowerCase()) return false;
      if (organizer && !event.organizer.toLowerCase().includes(organizer.toLowerCase())) return false;
      if (search) {
        const searchable = [event.title, event.description, event.category, event.organizer, event.venue].join(' ').toLowerCase();
        if (!searchable.includes(search.toLowerCase())) return false;
      }
      return true;
    });

    const sortBy = String(req.query.sort || 'score').toLowerCase();
    if (['score', 'rank'].includes(sortBy)) filtered.sort((a, b) => b.score - a.score || b.composite_score - a.composite_score);
    else if (['date', 'upcoming', 'start_time'].includes(sortBy)) filtered.sort((a, b) => new Date(a.startTime) - new Date(b.startTime));
    else if (['turnout', 'attendance'].includes(sortBy)) filtered.sort((a, b) => b.turnout_count - a.turnout_count);
    else if (['reviews', 'rating'].includes(sortBy)) filtered.sort((a, b) => b.review_count - a.review_count || (b.avg_rating || 0) - (a.avg_rating || 0));
    else if (sortBy === 'title') filtered.sort((a, b) => a.title.localeCompare(b.title));
    else if (sortBy === 'newest') filtered.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

    const page = Math.max(1, Number.parseInt(req.query.page, 10) || 1);
    const limit = Math.min(100, Math.max(1, Number.parseInt(req.query.limit, 10) || 20));
    const count = filtered.length;
    const interests = String(req.query.interests || '').split(',').map((item) => item.trim()).filter(Boolean);
    if (interests.length) filtered = recommendEvents(interests, filtered, count);
    return res.json({ events: filtered.slice((page - 1) * limit, page * limit), count, page, pages: Math.ceil(count / limit) });
  } catch (error) {
    return next(error);
  }
}

async function getScoredEvents() {
  const [events, reviews, checkins] = await Promise.all([
    Event.find({}).lean(),
    Review.find({}).select('eventId userId rating').lean(),
    Checkin.find({}).select('eventId').lean()
  ]);
  return enrichEvents(events, reviews, checkins);
}

async function recommendations(req, res, next) {
  try {
    const interests = String(req.query.interests || '').split(',').map((item) => item.trim()).filter(Boolean);
    const topN = Math.min(100, Math.max(1, Number.parseInt(req.query.top_n, 10) || 5));
    const events = await getScoredEvents();
    const items = recommendEvents(interests, events, topN);
    return res.json({ recommendations: items, count: items.length });
  } catch (error) {
    return next(error);
  }
}

async function listCategories(req, res, next) {
  try {
    const categories = await Event.distinct('category', { category: { $nin: ['', null] } });
    return res.json({ categories: categories.sort((a, b) => a.localeCompare(b)) });
  } catch (error) {
    return next(error);
  }
}

async function getEvent(req, res, next) {
  try {
    if (!mongoose.isValidObjectId(req.params.eventId)) {
      return res.status(400).json({ message: 'Invalid event id' });
    }
    const events = await getScoredEvents();
    const event = events.find((item) => item.id === req.params.eventId);
    if (!event) return res.status(404).json({ message: 'Event not found' });
    return res.json({ event });
  } catch (error) {
    return next(error);
  }
}

async function listMyEvents(req, res, next) {
  try {
    if (req.user.role !== 'community') {
      return res.status(403).json({ message: 'Only community organizers can view hosted events' });
    }
    const events = await getScoredEvents();
    const mine = events.filter((event) => event.organizer_id === String(req.user._id));
    return res.json({ events: mine, count: mine.length });
  } catch (error) {
    return next(error);
  }
}

async function createEvent(req, res, next) {
  try {
    if (req.user.role !== 'community') {
      return res.status(403).json({ message: 'Only community organizers can create events' });
    }
    const payload = eventPayload(req.body, { creating: true });
    payload.location = parseCoordinates(payload.location || {});
    payload.organizer = payload.organizer || req.user.name || req.user.email.split('@')[0];
    payload.organizerId = req.user._id;
    const event = await Event.create(payload);
    return res.status(201).json({ message: 'Event created successfully', event: serializeEvent(event) });
  } catch (error) {
    return next(error);
  }
}

async function updateEvent(req, res, next) {
  try {
    if (req.user.role !== 'community') {
      return res.status(403).json({ message: 'Only community organizers can update events' });
    }
    if (!mongoose.isValidObjectId(req.params.eventId)) {
      return res.status(400).json({ message: 'Invalid event id' });
    }
    const event = await Event.findById(req.params.eventId);
    if (!event) return res.status(404).json({ message: 'Event not found' });
    if (!event.organizerId.equals(req.user._id)) {
      return res.status(403).json({ message: 'You are not authorized to update this event' });
    }

    const payload = eventPayload(req.body);
    if (payload.location) payload.location = parseCoordinates(payload.location);
    if (!Object.keys(payload).length) return res.status(400).json({ message: 'No valid fields provided for update' });
    Object.assign(event, payload);
    await event.save();
    return res.json({ message: 'Event updated successfully', event: serializeEvent(event) });
  } catch (error) {
    return next(error);
  }
}

async function deleteEvent(req, res, next) {
  try {
    if (req.user.role !== 'community') {
      return res.status(403).json({ message: 'Only community organizers can delete events' });
    }
    if (!mongoose.isValidObjectId(req.params.eventId)) {
      return res.status(400).json({ message: 'Invalid event id' });
    }
    const event = await Event.findById(req.params.eventId);
    if (!event) return res.status(404).json({ message: 'Event not found' });
    if (!event.organizerId.equals(req.user._id)) {
      return res.status(403).json({ message: 'You are not authorized to delete this event' });
    }
    await Promise.all([
      Review.deleteMany({ eventId: event._id }),
      Checkin.deleteMany({ eventId: event._id })
    ]);
    await event.deleteOne();
    return res.json({ message: 'Event deleted successfully' });
  } catch (error) {
    return next(error);
  }
}

module.exports = { listEvents, listCategories, recommendations, getEvent, listMyEvents, createEvent, updateEvent, deleteEvent };
