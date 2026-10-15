# EventRank Backend

Express and MongoDB API with JWT authentication.

## Database design

MongoDB stores four collections through the Mongoose models:

| Collection | Stored data | Relationships and constraints |
| --- | --- | --- |
| `users` | Name, normalized email, bcrypt password hash | Email is unique. Password hashes are excluded from normal queries and API responses. |
| `events` | Event details, organizer display name and user reference, venue coordinates, start time, capacity | Each event references its organizer in `users`. Category, organizer, and start time are indexed; event text fields have a text index. |
| `reviews` | Event and user references, rating, comment | One review per user per event, enforced by a unique compound index. |
| `checkins` | Event and user references, verified flag | One check-in per user per event, enforced by a unique compound index. |

Reviews and check-ins refer to events and users by MongoDB ObjectId. Removing an event also removes its reviews and check-ins in the API. Mongoose timestamps provide `createdAt` and `updatedAt` for all four collections.

## Setup

1. Install Node.js 18 or later and start a MongoDB instance.
2. From this directory, run `npm install`.
3. Copy `.env.example` to `.env` and set unique, random `JWT_SECRET` and `QR_SECRET` values of at least 32 characters. Keep the secrets separate.
4. Start the API with `npm run dev` (or `npm start`).

The API listens on port `5000` by default. `GET /api/health` checks that the HTTP server is responding.

## Authentication routes

| Method | Path | Body | Result |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register` | `{ "name": "Sam", "email": "sam@example.com", "password": "at-least-8-chars" }` | Creates an account and returns `{ user, token }` |
| `POST` | `/api/auth/login` | `{ "email": "sam@example.com", "password": "..." }` | Returns `{ user, token }` |
| `GET` | `/api/auth/me` | Bearer token in `Authorization` header | Returns the authenticated user |

## Event routes

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/events` | Public | Search/filter events with `search`, `category`, `organizer`, `sort`, `page`, and `limit` query parameters |
| `GET` | `/api/events/categories` | Public | List categories currently in use |
| `GET` | `/api/events/recommendations` | Public | Recommend events using interests from query parameters |
| `GET` | `/api/events/:eventId` | Public | Fetch one event |
| `POST` | `/api/events` | Authenticated | Create an event |
| `PUT` | `/api/events/:eventId` | Event organizer | Update an event |
| `DELETE` | `/api/events/:eventId` | Event organizer | Delete an event |

Event creation accepts `title`, `venue`, and `startTime` (ISO 8601), plus optional `description`, `category`, `capacity`, `organizer`, and `location: { "lat": 0, "lng": 0 }`.

Event listings include credibility-weighted review scores, predicted scores for unrated events, verified turnout counts, and composite EventRank scores. Use `interests` as a comma-separated query parameter on `/api/events` or `/api/events/recommendations` for TF-IDF recommendations.

## Reviews and verified check-ins

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/events/:eventId/reviews` | Public | List reviews and whether each author checked in |
| `POST` | `/api/events/:eventId/reviews` | Authenticated | Create or update the signed-in user's 1–10 rating and comment |
| `DELETE` | `/api/reviews/:reviewId` | Review author | Delete a review |
| `GET` | `/api/events/:eventId/insights` | Public | Return average rating, verified turnout, and composite rank |
| `GET` | `/api/insights` | Public | Return campus-wide event, review, attendance, and sentiment summaries |
| `GET` | `/api/checkins/events/:eventId/qr-data` | Event organizer | Create a short-lived HMAC-signed QR token and check-in URL |
| `POST` | `/api/checkins` | Authenticated | Verify QR token, event time, and venue radius, then record one check-in per user |
| `GET` | `/api/checkins/status?eventId=:id` | Optional auth | Check the signed-in user's attendance status |
| `GET` | `/api/checkins/events/:eventId/checkins` | Event organizer | View verified turnout |

Compatibility routes are also available at `GET /api/events/:eventId/qr-data`, `GET /api/events/:eventId/checkins`, `POST /api/checkin`, and `GET /api/checkin/status`.

QR configuration uses `QR_SECRET` (which should differ from `JWT_SECRET`), `QR_WINDOW_SECONDS`, `EARLY_CHECKIN_MINUTES`, `VENUE_RADIUS_METERS`, and `FRONTEND_URL`.

Review responses include a sentiment label and score. Review insights summarize sentiment and extract short pros/cons from comments.

## Postman checks

Import `postman/EventRank.postman_collection.json` into Postman. The `Health` folder checks the live API without a database. The full collection creates a temporary test account, event, check-in, and review, then deletes the event. Run `npm run api:check` for the health request or `npm run api:check:all` with MongoDB running for the end-to-end flow. The collection uses `http://localhost:5000` by default.

Example authenticated request header: `Authorization: Bearer <token>`.

Passwords are hashed before storage. The API never returns password hashes.
