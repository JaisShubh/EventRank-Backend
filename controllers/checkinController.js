const crypto = require('crypto');
const mongoose = require('mongoose');
const Checkin = require('../models/Checkin');
const Event = require('../models/Event');

function qrWindowSeconds() {
  return Math.max(30, Number.parseInt(process.env.QR_WINDOW_SECONDS, 10) || 60);
}

function qrSecret() {
  return process.env.QR_SECRET || process.env.JWT_SECRET;
}

function signWindow(eventId, timeSlice) {
  return crypto.createHmac('sha256', qrSecret()).update(`${eventId}:${timeSlice}`).digest('hex').slice(0, 32);
}

function createQrToken(eventId, timestamp = Date.now()) {
  const window = qrWindowSeconds();
  const timeSlice = Math.floor(timestamp / 1000 / window);
  const expiresIn = window - (Math.floor(timestamp / 1000) % window);
  return { token: `${timeSlice}.${signWindow(eventId, timeSlice)}`, expiresIn, window };
}

function verifyQrToken(eventId, token) {
  if (typeof token !== 'string') return false;
  const match = token.match(/^(\d+)\.([a-f\d]{32})$/i);
  if (!match) return false;
  const tokenSlice = Number(match[1]);
  const currentSlice = Math.floor(Date.now() / 1000 / qrWindowSeconds());
  if (Math.abs(currentSlice - tokenSlice) > 1) return false;
  const expected = Buffer.from(signWindow(eventId, tokenSlice), 'hex');
  const actual = Buffer.from(match[2], 'hex');
  return expected.length === actual.length && crypto.timingSafeEqual(expected, actual);
}

function distanceMeters(lat1, lng1, lat2, lng2) {
  const radius = 6371000;
  const toRad = (value) => (value * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * radius * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

async function eventForOwner(eventId, userId) {
  const event = await Event.findById(eventId);
  return event && event.organizerId.equals(userId) ? event : null;
}

async function getQrData(req, res, next) {
  try {
    if (!mongoose.isValidObjectId(req.params.eventId)) return res.status(400).json({ message: 'Invalid event id' });
    const event = await eventForOwner(req.params.eventId, req.user._id);
    if (!event) return res.status(404).json({ message: 'Event not found or you are not its organizer' });
    const { token, expiresIn, window } = createQrToken(String(event._id));
    const baseUrl = (process.env.FRONTEND_URL || 'http://localhost:5173').replace(/\/$/, '');
    const checkinUrl = `${baseUrl}/checkin?eventId=${event._id}&token=${encodeURIComponent(token)}`;
    res.set('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    return res.json({ event_id: String(event._id), token, checkin_url: checkinUrl, window_seconds: window, expires_in_seconds: expiresIn });
  } catch (error) {
    return next(error);
  }
}

async function createCheckin(req, res, next) {
  try {
    const eventId = String(req.body?.eventId || req.body?.event_id || '');
    if (!mongoose.isValidObjectId(eventId)) return res.status(400).json({ message: 'A valid eventId is required' });
    const event = await Event.findById(eventId);
    if (!event) return res.status(404).json({ message: 'Event not found' });

    if (!verifyQrToken(String(event._id), req.body?.token)) {
      return res.status(400).json({ message: 'A current event QR token is required' });
    }
    const openAt = event.startTime.getTime() - (Math.max(0, Number.parseInt(process.env.EARLY_CHECKIN_MINUTES, 10) || 60) * 60 * 1000);
    if (Date.now() < openAt) return res.status(400).json({ message: 'Check-in is not open yet' });

    const lat = Number(req.body?.lat);
    const lng = Number(req.body?.lng);
    const venueLat = event.location?.lat;
    const venueLng = event.location?.lng;
    if (![lat, lng, venueLat, venueLng].every(Number.isFinite)) {
      return res.status(400).json({ message: 'Valid venue and device coordinates are required' });
    }
    if (lat < -90 || lat > 90 || venueLat < -90 || venueLat > 90 || lng < -180 || lng > 180 || venueLng < -180 || venueLng > 180) {
      return res.status(400).json({ message: 'Coordinates are out of range' });
    }
    const radius = Math.max(1, Number.parseInt(process.env.VENUE_RADIUS_METERS, 10) || 100);
    const distance = distanceMeters(lat, lng, venueLat, venueLng);
    if (distance > radius) return res.status(400).json({ message: 'You are outside the check-in radius', distance_meters: Math.round(distance), allowed_radius: radius });

    const filter = { eventId: event._id, userId: req.user._id };
    const existing = await Checkin.findOne(filter);
    if (existing) return res.json({ message: 'Already checked in', already_checked_in: true, verified: true, checkin: existing });
    try {
      const checkin = await Checkin.create(filter);
      return res.status(201).json({ message: 'Check-in successful', verified: true, checkin });
    } catch (error) {
      if (error.code === 11000) {
        const checkin = await Checkin.findOne(filter);
        return res.json({ message: 'Already checked in', already_checked_in: true, verified: true, checkin });
      }
      throw error;
    }
  } catch (error) {
    return next(error);
  }
}

async function getCheckinStatus(req, res, next) {
  try {
    if (!req.user) return res.json({ authenticated: false, checked_in: false, checkin: null });
    const eventId = String(req.query.eventId || req.query.event_id || '');
    if (!mongoose.isValidObjectId(eventId)) return res.status(400).json({ message: 'A valid eventId query parameter is required' });
    const checkin = await Checkin.findOne({ eventId, userId: req.user._id });
    return res.json({ authenticated: true, checked_in: Boolean(checkin), checkin: checkin || null });
  } catch (error) {
    return next(error);
  }
}

async function listEventCheckins(req, res, next) {
  try {
    if (!mongoose.isValidObjectId(req.params.eventId)) return res.status(400).json({ message: 'Invalid event id' });
    const event = await eventForOwner(req.params.eventId, req.user._id);
    if (!event) return res.status(404).json({ message: 'Event not found or you are not its organizer' });
    const checkins = await Checkin.find({ eventId: event._id }).select('userId createdAt verified').sort({ createdAt: -1 });
    return res.json({ event_id: String(event._id), turnout_count: checkins.length, checkins });
  } catch (error) {
    return next(error);
  }
}

async function listMyCheckins(req, res, next) {
  try {
    const checkins = await Checkin.find({ userId: req.user._id, verified: true })
      .sort({ createdAt: -1 })
      .populate('eventId', 'title category organizer venue startTime');
    return res.json({ checkins });
  } catch (error) {
    return next(error);
  }
}

module.exports = { getQrData, createCheckin, getCheckinStatus, listEventCheckins, listMyCheckins };
