# Cine Crowd (MovieWeb App)

![Cine Crowd Screenshot](static/img/screenshotCineCrowd.png)

Cine Crowd is a Flask-based web application for discovering, rating, and discussing movies. It uses SQLAlchemy ORM for data persistence and offers both a user-friendly web UI and a JSON-based REST API.

## Project Structure

* **app.py**: Main Flask application with routes and UI logic.
* **models.py**: SQLAlchemy ORM models:

  * `User`: application users.
  * `Movie`: movie metadata and community ratings.
  * `UserMovie`: association table with personal user ratings.
  * `Comment`: user comments on movies.
* **datamanager/**: Data access layer:

  * `DataManagerInterface`: abstract interface for CRUD operations.
  * `SQLiteDataManager`: concrete implementation using SQLAlchemy/SQLite.
* **api/**: Blueprint for JSON API endpoints (`routes.py`).
* **templates/**: Jinja2 templates for UI pages.
* **static/**: CSS, JavaScript, and image assets.

## Core Classes

* **DataManagerInterface**: Defines methods for creating, reading, updating, and deleting users, movies, ratings, and comments.
* **SQLiteDataManager**: Implements `DataManagerInterface` with SQLAlchemy sessions.
* **Models**: ORM classes in `models.py` representing database tables and their relationships.

## API Overview

**Base URL:** `<host>/api/`

All endpoints return JSON in the structure:

```json
{
  "success": true,
  "data": { ... },
  "message": "Info"
}
```

### Users

* `GET /api/users` — list all users.
* `GET /api/users/<user_id>` — user details and movie list.
* `GET /api/users/<user_id>/movies` — movies for a user.
* `POST /api/users/<user_id>/movies` — add movie to user list (CSRF token required).
* `PUT /api/users/<user_id>/movies/<movie_id>` — update user rating.
* `DELETE /api/users/<user_id>/movies/<movie_id>` — remove movie from user.

### Movies

* `GET /api/movies` — list all movies.
* `GET /api/movies/<movie_id>` — movie details with comments.
* `GET /api/movies/<movie_id>/comments` — list comments.
* `POST /api/movies/<movie_id>/comments` — add a comment (CSRF token required).
* `POST /api/check_or_create_movie_by_imdb` — check for or add a movie by IMDb ID.

### Utilities

* `GET /api/omdb_proxy?title=<>&year=<>` — proxy search request to the external OMDb API.

## Getting Started

1. Copy `.env.example` to `.env` and set `DATABASE_URI`, `SECRET_KEY`, `OMDB_API_KEY`, and `OPENROUTER_API_KEY`.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```
3. Initialize the database:

   ```bash
   python init_db.py
   ```
4. Run the server:

   ```bash
   flask run
   ```

Enjoy exploring Cine Crowd—your ultimate movie companion!
