"""
api/routes.py
API routes for MovieWeb application.
"""

import os
import time
import json
import requests
from flask import Blueprint, jsonify, request, current_app
from functools import wraps
from dotenv import load_dotenv
from datamanager.sqlite_data_manager import SQLiteDataManager

load_dotenv()
OMDB_API_KEY = os.getenv("OMDB_API_KEY")

api = Blueprint("api", __name__)
data_manager = SQLiteDataManager()

cache = {}
CACHE_TIMEOUT = 300


def cache_response(timeout=CACHE_TIMEOUT):
    """Cache API responses for a given timeout (seconds)."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            key = f"{f.__name__}:{args}:{kwargs}"
            if key in cache:
                ts, resp = cache[key]
                if time.time() - ts < timeout:
                    return resp
            resp = f(*args, **kwargs)
            cache[key] = (time.time(), resp)
            return resp
        return decorated
    return decorator


def handle_api_error(f):
    """Wrap endpoint to catch exceptions and return JSON error."""
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            current_app.logger.error(
                f"API error in '{f.__name__}': {e}", exc_info=True
            )
            return jsonify({
                "success": False,
                "message": "Internal server error."
            }), 500
    return decorated


@api.route("/users")
@handle_api_error
@cache_response()
def get_users():
    """Return list of users with movie counts."""
    users = data_manager.get_all_users()
    result = []
    for u in users:
        result.append({
            "id": u.id,
            "name": u.name,
            "movie_count": len(u.movies)
        })
    current_app.logger.info(f"Retrieved {len(result)} users.")
    return jsonify({"success": True, "users": result}), 200


@api.route("/users/<int:user_id>")
@handle_api_error
@cache_response()
def get_user(user_id):
    """Return details of a specific user and their movies."""
    u = data_manager.get_user_by_id(user_id)
    if not u:
        return jsonify({"success": False, "message": "User not found"}), 404
    movies = []
    for rel in u.movies:
        m = rel.movie
        movies.append({
            "id": m.id,
            "title": m.title,
            "director": m.director,
            "year": m.year,
            "community_rating": m.community_rating,
            "community_rating_count": m.community_rating_count,
            "poster_url": m.poster_url,
            "user_rating": rel.user_rating
        })
    return jsonify({
        "success": True,
        "user": {"id": u.id, "name": u.name, "movies": movies}
    }), 200


@api.route("/users/<int:user_id>/movies")
@handle_api_error
@cache_response()
def get_user_movies(user_id):
    """Return all movies of a user with personal ratings."""
    u = data_manager.get_user_by_id(user_id)
    if not u:
        return jsonify({"success": False, "message": "User not found"}), 404
    rels = data_manager.get_user_movie_relations(user_id)
    movies = []
    for r in rels:
        m = r.movie
        movies.append({
            "id": m.id,
            "title": m.title,
            "director": m.director,
            "year": m.year,
            "community_rating": m.community_rating,
            "community_rating_count": m.community_rating_count,
            "poster_url": m.poster_url,
            "user_rating": r.user_rating
        })
    return jsonify({
        "success": True,
        "user_id": u.id,
        "user_name": u.name,
        "movies": movies
    }), 200


@api.route("/movies")
@handle_api_error
@cache_response()
def get_movies():
    """Return list of all movies."""
    movies = data_manager.get_all_movies()
    result = []
    for m in movies:
        result.append({
            "id": m.id,
            "title": m.title,
            "director": m.director,
            "year": m.year,
            "community_rating": m.community_rating,
            "community_rating_count": m.community_rating_count,
            "poster_url": m.poster_url
        })
    return jsonify({"success": True, "movies": result}), 200


@api.route("/movies/<int:movie_id>")
@handle_api_error
@cache_response()
def get_movie(movie_id):
    """Return details of a specific movie, including comments."""
    m = data_manager.get_movie_by_id(movie_id)
    if not m:
        return jsonify({"success": False, "message": "Movie not found"}), 404
    comments = []
    for c in data_manager.get_comments_for_movie(movie_id):
        comments.append({
            "id": c.id,
            "text": c.text,
            "user": c.user.name,
            "created_at": c.created_at.isoformat(),
            "likes_count": c.likes_count
        })
    return jsonify({
        "success": True,
        "movie": {
            "id": m.id,
            "title": m.title,
            "director": m.director,
            "year": m.year,
            "community_rating": m.community_rating,
            "community_rating_count": m.community_rating_count,
            "poster_url": m.poster_url,
            "plot": m.plot,
            "runtime": m.runtime,
            "awards": m.awards,
            "language": m.language,
            "genre": m.genre,
            "actors": m.actors,
            "writer": m.writer,
            "country": m.country,
            "metascore": m.metascore,
            "rated_omdb": m.rated_omdb,
            "imdb_id": m.imdb_id,
            "comments": comments
        }
    }), 200


@api.route("/movies/<int:movie_id>/comments")
@handle_api_error
@cache_response()
def get_movie_comments(movie_id):
    """Return all comments for a specific movie."""
    m = data_manager.get_movie_by_id(movie_id)
    if not m:
        return jsonify({"success": False, "message": "Movie not found"}), 404
    comments = []
    for c in data_manager.get_comments_for_movie(movie_id):
        comments.append({
            "id": c.id,
            "text": c.text,
            "user": c.user.name,
            "created_at": c.created_at.isoformat(),
            "likes_count": c.likes_count
        })
    return jsonify({
        "success": True,
        "movie_id": movie_id,
        "comments": comments
    }), 200


@api.route("/users/<int:user_id>/movies", methods=["POST"])
@handle_api_error
def add_movie_api(user_id):
    """
    POST /api/users/<user_id>/movies
    Add a new movie to a user's favorites via JSON payload.
    """
    u = data_manager.get_user_by_id(user_id)
    if not u:
        current_app.logger.warning(f"User {user_id} not found for add_movie_api")
        return jsonify({"success": False, "message": "User not found"}), 404

    data = request.get_json() or {}
    title = data.get("title")
    if not title:
        return jsonify({"success": False, "message": "Title required"}), 400

    director = data.get("director")
    year = None
    if data.get("year"):
        try:
            year = int(data["year"])
        except ValueError:
            return jsonify({"success": False, "message": "Invalid year format"}), 400

    rating = None
    if data.get("rating") is not None:
        try:
            rating = float(data["rating"])
            if not (0 <= rating <= 5):
                return jsonify({"success": False, "message": "Rating must be 0–5"}), 400
        except ValueError:
            return jsonify({"success": False, "message": "Invalid rating format"}), 400

    poster_url = data.get("poster_url")
    imdb_id = data.get("imdb_id")
    plot = data.get("plot")
    runtime = data.get("runtime")
    awards = data.get("awards")
    languages = data.get("language")
    genre = data.get("genre")
    actors = data.get("actors")
    writer = data.get("writer")
    country = data.get("country")
    metascore = data.get("metascore")
    rated_omdb = data.get("rated")
    omdb_init = None
    if data.get("omdb_initial_rating_5_star"):
        try:
            tmp = float(data["omdb_initial_rating_5_star"])
            omdb_init = tmp if 0 <= tmp <= 5 else None
        except ValueError:
            omdb_init = None

    link = data_manager.add_movie(
        user_id=user_id,
        title=title,
        director=director,
        year=year,
        user_specific_rating=rating,
        poster_url=poster_url,
        imdb_id=imdb_id,
        plot=plot,
        runtime=runtime,
        awards=awards,
        languages=languages,
        genre=genre,
        actors=actors,
        writer=writer,
        country=country,
        metascore=metascore,
        rated=rated_omdb,
        omdb_rating_for_community=omdb_init
    )

    if link and link.movie:
        current_app.logger.info(f"Added movie {link.movie.id} to user {user_id}.")
        return jsonify({
            "success": True,
            "message": "Movie added to user list",
            "movie_id": link.movie.id,
            "user_movie_id": link.id
        }), 201

    current_app.logger.warning(f"Could not add movie '{title}' to user {user_id}.")
    return jsonify({
        "success": False,
        "message": "Failed to add movie; might already exist or error occurred"
    }), 409


@api.route("/omdb_proxy")
@handle_api_error
def omdb_proxy():
    """
    Proxy OMDb API requests to hide API key.
    Requires 'title' or 'imdb_id' query param, optional 'year' and 'plot'.
    """
    if not OMDB_API_KEY:
        current_app.logger.error("OMDb API key not configured for proxy.")
        return jsonify({"success": False, "message": "OMDb key not configured"}), 503

    title = request.args.get("title")
    imdb_id = request.args.get("imdb_id")
    if not title and not imdb_id:
        return jsonify({"success": False, "message": "title or imdb_id required"}), 400

    year = request.args.get("year")
    plot = request.args.get("plot", "short")
    params = {"apikey": OMDB_API_KEY, "plot": plot}
    if title:
        params["t"] = title
    if imdb_id:
        params["i"] = imdb_id
    if year:
        params["y"] = year

    current_app.logger.info(f"OMDb proxy params: {params}")
    try:
        resp = requests.get("http://www.omdbapi.com/", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("Response") == "True":
            current_app.logger.info("OMDb proxy success")
            return jsonify({"success": True, "data": data})
        err = data.get("Error", "Unknown error from OMDb")
        current_app.logger.warning(f"OMDb proxy returned false: {err}")
        return jsonify({"success": False, "message": err, "data": data}), 200

    except requests.exceptions.Timeout:
        current_app.logger.warning(f"OMDb proxy timeout for params: {params}")
        return jsonify({"success": False, "message": "OMDb request timed out"}), 504
    except requests.exceptions.HTTPError as http_err:
        current_app.logger.error(f"OMDb HTTP error: {http_err}. Response: {resp.text}")
        err_msg = f"OMDb HTTP error: {http_err}"
        try:
            err_data = resp.json()
            if "Error" in err_data:
                err_msg = err_data["Error"]
        except ValueError:
            pass
        return jsonify({"success": False, "message": err_msg, "omdb_error_data": err_data if "err_data" in locals() else None}), resp.status_code
    except requests.exceptions.RequestException as req_err:
        current_app.logger.error(f"OMDb proxy request failed: {req_err}")
        return jsonify({"success": False, "message": f"Failed to connect to OMDb: {req_err}"}), 502
    except ValueError as json_err:
        current_app.logger.error(f"OMDb JSON decode error: {json_err}. Response: {resp.text if 'resp' in locals() else 'N/A'}")
        return jsonify({"success": False, "message": "Failed to decode OMDb response"}), 500


@api.route("/check_or_create_movie_by_imdb", methods=["POST"])
@handle_api_error
def check_or_create_movie_by_imdb():
    """
    Check if movie by imdbID exists; if not, create globally using provided OMDb-like data.
    Expects JSON with 'imdbID' and OMDb fields.
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    imdb_id = data.get("imdbID")
    if not imdb_id:
        return jsonify({"success": False, "message": "imdbID required"}), 400

    m = data_manager.get_movie_by_imdb_id(imdb_id)
    if m:
        current_app.logger.info(f"Found movie {m.id} for imdbID {imdb_id}")
        return jsonify({"success": True, "data": {"status": "exists", "movie_id": m.id}}), 200

    current_app.logger.info(f"Creating movie for imdbID {imdb_id}")
    new_m = data_manager.add_movie_globally(movie_data=data)
    if new_m:
        current_app.logger.info(f"Created movie {new_m.id} for imdbID {imdb_id}")
        return jsonify({"success": True, "data": {"status": "created", "movie_id": new_m.id}}), 201

    current_app.logger.error(f"Failed to create movie for imdbID {imdb_id}")
    return jsonify({"success": False, "message": "Failed to create movie"}), 500
