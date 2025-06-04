"""
app.py
Main module for MovieWeb application.
"""

import json
import os
import re
from datetime import datetime

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    current_app,
    flash,
    jsonify,
    session,
    url_for,
    g,
)
from flask_wtf.csrf import CSRFProtect

from api.routes import api as api_blueprint
from datamanager.sqlite_data_manager import SQLiteDataManager
from models import Comment, db, Movie, User, UserMovie

load_dotenv()
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URI", "sqlite:///moviewebapp.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_secret")

csrf = CSRFProtect(app)
db.init_app(app)
app.register_blueprint(api_blueprint, url_prefix="/api")
data_manager = SQLiteDataManager()

AI_MOVIE_IDENTIFICATION_PROMPT_TEMPLATE = (
    "User input: '{user_input}'. Identify the single correct movie title or return "
    "'NO_CLEAR_MOVIE_TITLE_FOUND'."
)
MOVIE_RECOMMENDATION_PROMPT_TEMPLATE = (
    "Based on '{movie_title}', suggest 5 similar movie titles, one per line, no extra text."
    "{exclusion_clause}"
)
EXCLUSION_CLAUSE_TEMPLATE = (
    "\n\nExclude these titles:\n{movies_to_exclude_list_format}"
)
AI_RECOMMENDATION_HISTORY_SESSION_KEY = "ai_recommendation_history"
AI_RECOMMENDATION_HISTORY_LENGTH = 20
DEFAULT_AI_TEMPERATURE_RECOMMEND = 0.7
DEFAULT_AI_TEMPERATURE_INTERPRET = 0.3
NO_CLEAR_MOVIE_TITLE_MARKER = "NO_CLEAR_MOVIE_TITLE_FOUND_INTERNAL"

AI_MODEL_FOR_REQUESTS = "openai/gpt-3.5-turbo"
AI_MSG_OPENROUTER_KEY_MISSING = "OpenRouter API Key not configured."
AI_MSG_REQUEST_TIMEOUT = "AI request timed out."
AI_MSG_CONNECTION_ERROR_GENERIC = "Error connecting to AI."
AI_MSG_API_ERROR_DETAILED_TEMPLATE = "AI API Error: {error_message}."
AI_MSG_UNEXPECTED_ERROR_TEMPLATE = "Unexpected AI error: {error_message}."
AI_MSG_NO_SUGGESTIONS_LIST = "AI returned no suggestions."


def get_ai_interpreted_movie_title(
    user_input: str, temperature: float = DEFAULT_AI_TEMPERATURE_INTERPRET
) -> str:
    """
    Return AI-interpreted movie title or NO_CLEAR_MOVIE_TITLE_MARKER.
    """
    if not user_input:
        return NO_CLEAR_MOVIE_TITLE_MARKER

    prompt = AI_MOVIE_IDENTIFICATION_PROMPT_TEMPLATE.format(user_input=user_input)
    current_app.logger.debug(f"AI prompt:\n{prompt}")

    ai_list = ask_openrouter_for_movies(
        prompt_content=prompt, temperature=temperature, expected_responses=1
    )
    if not ai_list:
        current_app.logger.warning(f"No AI response for '{user_input}'")
        return NO_CLEAR_MOVIE_TITLE_MARKER

    title = ai_list[0]
    if title == "NO_CLEAR_MOVIE_TITLE_FOUND":
        current_app.logger.info(f"AI found no title for '{user_input}'")
        return NO_CLEAR_MOVIE_TITLE_MARKER

    low = title.lower()
    if "error" in low or "not configured" in low or "timed out" in low:
        current_app.logger.warning(f"AI returned error phrase: {title}")
        return NO_CLEAR_MOVIE_TITLE_MARKER

    current_app.logger.info(f"AI interpreted '{user_input}' as '{title}'")
    return title


@app.before_request
def load_logged_in_user():
    """Load logged-in user into g.user."""
    uid = session.get("user_id")
    g.user = data_manager.get_user_by_id(uid) if uid else None


@app.context_processor
def inject_user_status():
    """Make user login status and object available in templates."""
    return dict(g_is_user_logged_in=(g.user is not None), g_current_user=g.user)


@app.route("/")
def home():
    """Show home page with top movies."""
    top_movies = data_manager.get_top_movies()
    return render_template("home.html", top_movies=top_movies)


@app.route("/login", methods=["POST"])
def login():
    """Handle login via POST; expects 'username'. Return JSON."""
    username = request.form.get("username", "").strip()
    user = data_manager.get_user_by_name(username)
    if user:
        session["user_id"] = user.id
        current_app.logger.info(f"User '{username}' (ID: {user.id}) logged in.")
        return (
            jsonify(
                {
                    "success": True,
                    "redirect": f"/users/{user.id}",
                    "message": "Login successful.",
                }
            ),
            200,
        )

    current_app.logger.warning(f"Login failed for '{username}'")
    return (
        jsonify(
            {
                "success": False,
                "message": "User not found.",
            }
        ),
        401,
    )


@app.route("/register", methods=["POST"])
def register():
    """Handle registration via POST; expects 'username'. Return JSON."""
    username = request.form.get("username", "").strip()
    new_user = data_manager.add_user(username)
    if not new_user:
        if not username:
            current_app.logger.warning("Empty username at registration")
            return jsonify({"success": False, "message": "Username cannot be empty."}), 400
        current_app.logger.warning(f"Registration failed for '{username}'")
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Username invalid or exists.",
                }
            ),
            409,
        )

    session["user_id"] = new_user.id
    current_app.logger.info(f"User '{new_user.name}' (ID: {new_user.id}) registered.")
    return (
        jsonify(
            {
                "success": True,
                "redirect": f"/users/{new_user.id}",
                "message": "Registration successful.",
            }
        ),
        201,
    )


@app.route("/logout")
def logout():
    """Log out current user and redirect to home."""
    session.pop("user_id", None)
    g.user = None
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/users")
def list_users():
    """Show list of all users."""
    users = data_manager.get_all_users()
    return render_template("users.html", users=users)


@app.route("/users/<int:user_id>")
def list_user_movies(user_id):
    """Show a user's favorite movies."""
    try:
        user = data_manager.get_user_by_id(user_id)
        if not user:
            flash("User not found.", "warning")
            return redirect(url_for("list_users"))
        relations = data_manager.get_user_movie_relations(user_id)
    except Exception as err:
        current_app.logger.error(f"Error listing movies for user {user_id}: {err}")
        return render_template("500.html"), 500

    return render_template(
        "movies.html",
        user_movie_relations=relations,
        user=user,
        IS_USER_LOGGED_IN=True,
    )


@app.route("/add_user", methods=["GET", "POST"])
def add_user():
    """Admin/testing: add user via form."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Username cannot be empty.", "danger")
        else:
            new_user_obj = data_manager.add_user(name)
            if new_user_obj:
                flash(f'User "{new_user_obj.name}" added.', "success")
                return redirect(url_for("list_users"))
            flash(f'User "{name}" exists or is invalid.', "warning")
    return render_template("add_user.html")


def _prepare_movie_details_from_db_for_add_template(
    movie_id: int, user_id: int
) -> dict:
    """
    Build context from DB for 'add_movie' template given movie_id and user_id.
    """
    ctx = {"omdb": None, "omdb_details": None, "rating5": None, "user_search_input": None, "flash_message": None}
    m = data_manager.get_movie_by_id(movie_id)
    if m:
        ctx["omdb"] = {
            "Response": "True",
            "Title": m.title,
            "Year": str(m.year) if m.year else "N/A",
            "Poster": m.poster_url,
            "Director": m.director,
            "imdbRating": str(m.community_rating * 2) if m.community_rating is not None else "N/A",
        }
        ctx["omdb_details"] = {
            "plot": m.plot,
            "runtime": m.runtime,
            "awards": m.awards,
            "languages": m.language,
            "genre": m.genre,
            "actors": m.actors,
            "writer": m.writer,
            "country": m.country,
            "metascore": m.metascore,
            "rated": m.rated_omdb,
            "imdb_id": m.imdb_id,
        }
        if m.community_rating is not None:
            ctx["rating5"] = m.community_rating
        else:
            uml = data_manager.get_user_movie_link(user_id=user_id, movie_id=m.id)
            if uml and uml.user_rating is not None:
                ctx["rating5"] = uml.user_rating
        ctx["user_search_input"] = m.title
    else:
        ctx["flash_message"] = (f"Movie ID {movie_id} not found.", "danger")
    return ctx


def _fetch_movie_details_from_omdb_for_add_template(title: str) -> dict:
    """
    Query OMDb for title; build context for 'add_movie' template.
    """
    ctx = {"omdb": None, "omdb_details": None, "rating5": None, "ai_message": None, "flash_message": None}
    params = {"apikey": OMDB_API_KEY, "t": title}
    try:
        resp = requests.get("http://www.omdbapi.com/", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        ctx["omdb"] = data
    except requests.exceptions.RequestException as err:
        current_app.logger.error(f"OMDb request failed for '{title}': {err}")
        data = {"Response": "False", "Error": str(err)}
        ctx["omdb"] = data
        ctx["flash_message"] = (f"OMDb error for '{title}': {str(err)[:100]}.", "danger")

    if data.get("Response") == "True":
        ctx["omdb_details"] = {
            "plot": data.get("Plot"),
            "runtime": data.get("Runtime"),
            "awards": data.get("Awards"),
            "languages": data.get("Language"),
            "genre": data.get("Genre"),
            "actors": data.get("Actors"),
            "writer": data.get("Writer"),
            "country": data.get("Country"),
            "metascore": data.get("Metascore"),
            "rated": data.get("Rated"),
            "imdb_id": data.get("imdbID"),
        }
        raw_rating = data.get("imdbRating")
        if raw_rating and raw_rating != "N/A":
            try:
                rating10 = float(raw_rating)
                ctx["rating5"] = round(rating10 / 2 * 2) / 2
            except ValueError:
                pass
    else:
        err_msg = data.get("Error", "Unknown OMDb error")
        ctx["ai_message"] = f"OMDb no details for '{title}': {err_msg}"
        current_app.logger.warning(f"OMDb search failed for '{title}': {err_msg}")

    return ctx


def _get_ai_suggestion_for_add_movie_template(user_search_input: str) -> dict:
    """
    Return AI-suggested title and message for 'add_movie' flow.
    """
    ctx = {"ai_suggested_title": None, "ai_message": None}
    current_app.logger.info(f"AI search for '{user_search_input}'")
    result = get_ai_interpreted_movie_title(user_search_input)
    if result == NO_CLEAR_MOVIE_TITLE_MARKER or result is None:
        ctx["ai_message"] = "AI could not identify a movie title."
    else:
        ctx["ai_suggested_title"] = result
    return ctx


def _process_add_movie_form(
    form_data, user_id: int, source_movie_id: int, original_input: str
) -> tuple[bool, str, str, str]:
    """
    Process form data to add a movie. Return (success, message, category, redirect_url).
    """
    title = form_data.get("title_from_omdb", "").strip()
    if not title:
        return (
            False,
            "Movie title missing. Please search again.",
            "danger",
            url_for("add_movie", user_id=user_id, user_search_input=original_input),
        )

    director = form_data.get("director", "").strip()
    year_str = form_data.get("year", "").strip()
    rating_str = form_data.get("rating", "").strip()
    poster_url = form_data.get("poster_url", "").strip()
    plot = form_data.get("plot", "").strip()
    runtime = form_data.get("runtime", "").strip()
    awards = form_data.get("awards", "").strip()
    languages = form_data.get("languages", "").strip()
    genre = form_data.get("genre", "").strip()
    actors = form_data.get("actors", "").strip()
    writer = form_data.get("writer", "").strip()
    country = form_data.get("country", "").strip()
    metascore = form_data.get("metascore", "").strip()
    rated = form_data.get("rated", "").strip()
    imdb_id = form_data.get("imdb_id", "").strip()

    year = int(year_str) if year_str.isdigit() else None

    rating = None
    if rating_str:
        try:
            rating = float(rating_str)
            if not (0 <= rating <= 5):
                return (
                    False,
                    "Rating must be 0–5.",
                    "warning",
                    url_for("add_movie", user_id=user_id, user_search_input=original_input),
                )
        except ValueError:
            return (
                False,
                "Rating must be a number.",
                "warning",
                url_for("add_movie", user_id=user_id, user_search_input=original_input),
            )

    omdb_rating_str = form_data.get("omdb_suggested_rating", "")
    omdb_rating = None
    if omdb_rating_str:
        try:
            tmp = float(omdb_rating_str)
            omdb_rating = tmp if 0 <= tmp <= 5 else None
        except ValueError:
            pass

    added = data_manager.add_movie(
        user_id,
        title,
        director,
        year,
        rating,
        poster_url or None,
        plot=plot or None,
        runtime=runtime or None,
        awards=awards or None,
        languages=languages or None,
        genre=genre or None,
        actors=actors or None,
        writer=writer or None,
        country=country or None,
        metascore=metascore or None,
        rated=rated or None,
        imdb_id=imdb_id or None,
        omdb_rating_for_community=omdb_rating,
    )

    if added:
        return True, f"Movie '{title}' added.", "success", None

    fail_url = url_for("add_movie", user_id=user_id, user_search_input=original_input)
    if source_movie_id:
        fail_url = url_for("movie_page", movie_id=source_movie_id)
    return (
        False,
        f"Could not add '{title}'. It may already be in your list or an error occurred.",
        "danger",
        fail_url,
    )


@app.route("/users/<int:user_id>/add_movie", methods=["GET", "POST"])
def add_movie(user_id):
    """
    Route to add a movie for a user.
    GET: handle AI or OMDb lookup.
    POST: process form to add movie.
    """
    user = data_manager.get_user_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("list_users"))

    ctx = {
        "user": user,
        "current_year": datetime.now().year,
        "user_search_input_value": request.args.get("user_search_input", ""),
        "ai_suggested_title": None,
        "ai_message": None,
        "omdb": None,
        "omdb_details": None,
        "rating5": None,
        "show_details_form": False,
        "hide_initial_search_form": False,
        "source_movie_id_for_template": request.args.get("source_movie_id", type=int),
    }

    if request.method == "GET":
        mid = request.args.get("movie_to_add_id", type=int)
        title_search = request.args.get("title_for_omdb_search", "").strip()
        orig_input = request.args.get("user_search_input", "")

        if mid or title_search:
            ctx["hide_initial_search_form"] = True

        if mid:
            current_app.logger.info(f"User {user_id} adding movie ID {mid}")
            db_ctx = _prepare_movie_details_from_db_for_add_template(mid, user_id)
            ctx.update(db_ctx)
            if db_ctx.get("flash_message"):
                flash(db_ctx["flash_message"][0], db_ctx["flash_message"][1])
                if db_ctx["flash_message"][1] == "danger":
                    return redirect(url_for("list_user_movies", user_id=user_id))
            if db_ctx.get("omdb", {}).get("Response") == "True":
                ctx["show_details_form"] = True
            if db_ctx.get("user_search_input"):
                ctx["user_search_input_value"] = db_ctx["user_search_input"]

        elif title_search:
            current_app.logger.info(f"User {user_id} OMDb search '{title_search}'")
            ctx["user_search_input_value"] = orig_input
            omdb_ctx = _fetch_movie_details_from_omdb_for_add_template(title_search)
            ctx.update(omdb_ctx)
            if omdb_ctx.get("flash_message"):
                flash(omdb_ctx["flash_message"][0], omdb_ctx["flash_message"][1])
            if omdb_ctx.get("omdb", {}).get("Response") == "True":
                ctx["show_details_form"] = True

        elif ctx["user_search_input_value"]:
            ai_ctx = _get_ai_suggestion_for_add_movie_template(ctx["user_search_input_value"])
            ctx.update(ai_ctx)

        return render_template("add_movie.html", **ctx)

    # POST
    orig_input = request.form.get("original_user_search_input", "")
    src_mid = request.form.get("source_movie_id", type=int)
    success, message, category, fail_url = _process_add_movie_form(
        request.form, user_id, src_mid, orig_input
    )
    flash(message, category)
    if success:
        return redirect(url_for("movie_page", movie_id=src_mid)) if src_mid else redirect(
            url_for("list_user_movies", user_id=user_id)
        )
    return redirect(fail_url or url_for("add_movie", user_id=user_id, user_search_input=orig_input))


@app.route("/users/<int:user_id>/update_movie_rating/<int:movie_id>", methods=["GET", "POST"])
def update_movie_rating(user_id, movie_id):
    """
    GET: show current rating form.
    POST: update user's rating for movie.
    """
    if not g.user or g.user.id != user_id:
        flash("Can only edit your own ratings.", "danger")
        return redirect(url_for("home"))

    movie = data_manager.get_movie_by_id(movie_id)
    if not movie:
        flash(f"Movie ID {movie_id} not found.", "danger")
        return redirect(url_for("home"))

    uml = data_manager.get_user_movie_link(user_id=g.user.id, movie_id=movie.id)
    if not uml:
        flash(f"'{movie.title}' not in your list.", "warning")
        return redirect(url_for("movie_page", movie_id=movie.id))

    if request.method == "POST":
        rating_str = request.form.get("rating", "").strip()
        new_rating = None
        if rating_str:
            try:
                new_rating = float(rating_str)
                if not (0 <= new_rating <= 5):
                    flash("Rating must be 0–5.", "warning")
                    return redirect(url_for("movie_page", movie_id=movie.id))
            except ValueError:
                flash("Rating must be a number.", "warning")
                return redirect(url_for("movie_page", movie_id=movie.id))

        success = data_manager.update_user_rating_for_movie(
            user_id=g.user.id, movie_id=movie.id, new_rating=new_rating
        )
        if success:
            flash(f"Your rating for '{movie.title}' updated.", "success")
            return redirect(url_for("list_user_movies", user_id=g.user.id))
        flash("Could not update rating.", "error")
        return redirect(url_for("movie_page", movie_id=movie.id))

    return render_template(
        "update_movie_rating.html",
        user=g.user,
        movie=movie,
        current_user_rating=uml.user_rating,
    )


@app.route("/users/<int:user_id>/delete_movie/<int:movie_id>", methods=["POST"])
def delete_movie(user_id, movie_id):
    """
    Delete a movie from a user's list.
    """
    try:
        success = data_manager.delete_movie_from_user_list(user_id=user_id, movie_id=movie_id)
    except Exception as err:
        current_app.logger.error(f"Delete movie error for user {user_id}, movie {movie_id}: {err}")
        flash("Error deleting movie.", "danger")
        return redirect(url_for("list_user_movies", user_id=user_id))

    if success:
        flash("Movie removed from your list.", "success")
    else:
        flash("Could not remove movie.", "warning")
    return redirect(url_for("list_user_movies", user_id=user_id))


@app.route("/movie/<int:movie_id>")
def movie_details(movie_id):
    """
    JSON endpoint: return movie details and comments.
    """
    movie = data_manager.get_movie_by_id(movie_id)
    if not movie:
        current_app.logger.warning(f"Movie ID {movie_id} not found for JSON.")
        return jsonify({"success": False, "message": "Movie not found"}), 404

    comments = data_manager.get_comments_for_movie(movie_id)
    movie_data = {
        "id": movie.id,
        "title": movie.title,
        "director": movie.director,
        "year": movie.year,
        "community_rating": movie.community_rating,
        "community_rating_count": movie.community_rating_count,
        "plot": movie.plot,
        "genre": movie.genre,
        "runtime": movie.runtime,
        "poster_url": movie.poster_url,
        "imdb_id": movie.imdb_id,
    }
    comments_data = [
        {
            "id": c.id,
            "text": c.text,
            "user": c.user.name,
            "created_at": c.created_at.isoformat(),
        }
        for c in comments
    ]

    current_app.logger.info(f"Returned JSON for movie {movie_id}.")
    return (
        jsonify({"success": True, "data": {"movie": movie_data, "comments": comments_data}}),
        200,
    )


@app.route("/movie/<int:movie_id>/comment", methods=["POST"])
def add_movie_comment(movie_id):
    """
    JSON endpoint: add comment to movie. Requires login.
    """
    if "user_id" not in session:
        current_app.logger.warning(f"Unauthenticated comment for movie {movie_id}.")
        return (
            jsonify({"success": False, "message": "Login required.", "data": None}),
            401,
        )

    uid = session["user_id"]
    text = request.form.get("text", "").strip()
    if not text:
        current_app.logger.warning(f"Empty comment for movie {movie_id} by user {uid}.")
        return (
            jsonify({"success": False, "message": "Comment cannot be empty.", "data": None}),
            400,
        )

    new_comment = data_manager.add_comment(movie_id=movie_id, user_id=uid, text=text)
    if new_comment:
        current_app.logger.info(f"User {uid} added comment {new_comment.id} to movie {movie_id}.")
        return (
            jsonify({"success": True, "message": "Comment added.", "data": {"comment_id": new_comment.id}}),
            201,
        )

    current_app.logger.error(f"Failed to add comment for movie {movie_id} by user {uid}.")
    return (
        jsonify({"success": False, "message": "Error adding comment.", "data": None}),
        500,
    )


@app.route("/api/docs")
def api_docs():
    """Render API documentation page."""
    return render_template("api_docs.html")


@app.route("/about")
def about():
    """Render About page."""
    return render_template("about.html")


@app.errorhandler(404)
def page_not_found(err):
    """Render 404 page."""
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(err):
    """Render 500 page."""
    return render_template("500.html"), 500


@app.route("/movie/<int:movie_id>/page")
def movie_page(movie_id):
    """
    Render detailed movie page.
    """
    try:
        movie = data_manager.get_movie_by_id(movie_id)
        if not movie:
            current_app.logger.warning(f"Movie {movie_id} not found for page.")
            return render_template("404.html"), 404

        rating = None
        in_list = False
        if g.user:
            uml = data_manager.get_user_movie_link(user_id=g.user.id, movie_id=movie.id)
            if uml:
                in_list = True
                rating = uml.user_rating

        return render_template(
            "movie_detail_page.html",
            movie=movie,
            user=g.user,
            is_movie_in_user_list=in_list,
            current_user_rating_for_movie=rating,
        )
    except Exception as err:
        current_app.logger.error(f"Error rendering movie page {movie_id}: {err}")
        return render_template("500.html"), 500


@app.route("/movie/<int:movie_id>/comment/page", methods=["POST"])
def add_movie_comment_page(movie_id):
    """
    Handle comment from movie detail page. Return JSON.
    """
    if "user_id" not in session:
        current_app.logger.warning(f"Unauthenticated comment for movie {movie_id}.")
        return jsonify({"success": False, "message": "Login required."}), 401

    uid = session["user_id"]
    current_app.logger.debug(f"Comment request for movie {movie_id} by user {uid}.")
    data = request.get_json()
    if not data:
        current_app.logger.warning(f"No JSON data for comment on movie {movie_id}.")
        return jsonify({"success": False, "message": "Expected JSON."}), 400

    text = data.get("comment_text", "").strip()
    current_app.logger.debug(f"Comment text: '{text}'")
    if not text:
        current_app.logger.warning(f"Empty comment for movie {movie_id} by user {uid}.")
        return jsonify({"success": False, "message": "Comment cannot be empty."}), 400

    new_comment = data_manager.add_comment(movie_id=movie_id, user_id=uid, text=text)
    if new_comment:
        current_app.logger.info(f"User {uid} added comment {new_comment.id} to movie {movie_id}.")
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Comment added.",
                    "comment_id": new_comment.id,
                    "comment_text": new_comment.text,
                    "user_name": new_comment.user.name,
                    "created_at": new_comment.created_at.isoformat(),
                }
            ),
            201,
        )

    current_app.logger.error(f"Failed to add comment for movie {movie_id} by user {uid}.")
    return jsonify({"success": False, "message": "Error adding comment."}), 500


@app.route("/user/add_movie_to_list/<int:movie_id>", methods=["POST"])
def add_movie_to_list(movie_id):
    """
    Add existing movie to logged-in user's list. Redirect to movie page.
    """
    if not g.user:
        flash("Login required to add movies.", "warning")
        return redirect(url_for("movie_page", movie_id=movie_id))

    success = data_manager.add_existing_movie_to_user_list(
        user_id=g.user.id, movie_id=movie_id
    )
    if success:
        m = data_manager.get_movie_by_id(movie_id)
        title = m.title if m else f"ID {movie_id}"
        flash(f"'{title}' added to your list.", "success")
    else:
        flash("Could not add movie.", "danger")

    return redirect(url_for("movie_page", movie_id=movie_id))


@app.route("/user/list/remove/<int:movie_id>", methods=["POST"], endpoint="remove_movie_from_list_explicit")
def remove_movie_from_list(movie_id):
    """
    Remove a movie from logged-in user's list. Redirect to movie page.
    """
    if not g.user:
        flash("Login required to remove movies.", "warning")
        return redirect(url_for("movie_page", movie_id=movie_id))

    success = data_manager.delete_movie_from_user_list(user_id=g.user.id, movie_id=movie_id)
    if success:
        flash(f"Movie (ID: {movie_id}) removed from your list.", "success")
    else:
        flash("Could not remove movie.", "danger")

    return redirect(url_for("movie_page", movie_id=movie_id))


@app.route("/movie/<int:movie_id>/ai_recommendations")
def get_ai_movie_recommendations_route(movie_id):
    """
    Return JSON list of AI-based recommendations for a movie.
    """
    movie = data_manager.get_movie_by_id(movie_id)
    if not movie:
        current_app.logger.warning(f"AI recs requested for invalid movie {movie_id}.")
        return jsonify({"success": False, "message": "Movie not found."}), 404

    uid = session.get("user_id", "Guest")
    history = session.get(AI_RECOMMENDATION_HISTORY_SESSION_KEY, [])
    exclusion_text = ""
    if history:
        exclude_list = "\n".join([f"- \"{t}\"" for t in history])
        exclusion_text = EXCLUSION_CLAUSE_TEMPLATE.format(movies_to_exclude_list_format=exclude_list)

    prompt = MOVIE_RECOMMENDATION_PROMPT_TEMPLATE.format(
        movie_title=movie.title, exclusion_clause=exclusion_text
    )
    current_app.logger.debug(f"AI prompt for recs (user {uid}, movie '{movie.title}'):\n{prompt}")

    try:
        temp_str = request.args.get("temp", str(DEFAULT_AI_TEMPERATURE_RECOMMEND))
        temp = float(temp_str) if 0.0 <= float(temp_str) <= 2.0 else DEFAULT_AI_TEMPERATURE_RECOMMEND
    except ValueError:
        current_app.logger.warning(f"Invalid temp '{request.args.get('temp')}', using default.")
        temp = DEFAULT_AI_TEMPERATURE_RECOMMEND

    ai_responses = ask_openrouter_for_movies(prompt_content=prompt, temperature=temp, expected_responses=5)
    if not ai_responses:
        current_app.logger.error(f"AI returned empty for recs (user {uid}, movie '{movie.title}').")
        return (
            jsonify(
                {"success": False, "message": AI_MSG_UNEXPECTED_ERROR_TEMPLATE.format(error_message="No AI data")}
            ),
            500,
        )

    markers = [
        AI_MSG_OPENROUTER_KEY_MISSING,
        AI_MSG_REQUEST_TIMEOUT,
        AI_MSG_CONNECTION_ERROR_GENERIC,
        AI_MSG_NO_SUGGESTIONS_LIST,
    ]
    if any(marker in ai_responses[0] for marker in markers) or AI_MSG_API_ERROR_DETAILED_TEMPLATE.split("{")[0] in ai_responses[0] or AI_MSG_UNEXPECTED_ERROR_TEMPLATE.split("{")[0] in ai_responses[0]:
        err_msg = ai_responses[0]
        current_app.logger.warning(f"AI recs error for user {uid}, movie '{movie.title}': {err_msg}")
        user_msg = err_msg
        if AI_MSG_OPENROUTER_KEY_MISSING in user_msg or "API Key" in user_msg:
            user_msg = "AI service misconfigured. Contact support."
        elif AI_MSG_NO_SUGGESTIONS_LIST in user_msg:
            user_msg = "AI found no recommendations."
        return jsonify({"success": False, "recommendations": [], "message": user_msg}), 503

    original_title = movie.title.lower().strip()
    filtered = [t for t in ai_responses if t.lower().strip() != original_title]

    seen = set()
    unique = []
    for t in filtered:
        key = t.lower().strip()
        if key not in seen:
            unique.append(t)
            seen.add(key)

    current_app.logger.info(f"AI recs (temp={temp}) for '{original_title}': orig={ai_responses}, filtered={unique}")

    recs_structured = [{"title": t, "year": None} for t in unique[:5] if isinstance(t, str) and t]

    if recs_structured:
        updated = list(history)
        for rec in recs_structured:
            title_str = rec["title"]
            if title_str.lower().strip() not in [h.lower().strip() for h in updated]:
                updated.append(title_str)
        if len(updated) > AI_RECOMMENDATION_HISTORY_LENGTH:
            updated = updated[-AI_RECOMMENDATION_HISTORY_LENGTH:]
        session[AI_RECOMMENDATION_HISTORY_SESSION_KEY] = updated
        current_app.logger.info(f"Updated AI history for user {uid}: {updated}")

        return (
            jsonify({"success": True, "recommendations": recs_structured, "message": "Loaded."}),
            200,
        )

    current_app.logger.warning(f"No valid recs after filtering for movie '{movie.title}'.")
    return (
        jsonify({"success": False, "recommendations": [], "message": "No valid recommendations."}),
        500,
    )


def ask_openrouter_for_movies(
    prompt_content: str, temperature: float, expected_responses: int = 5
) -> list[str]:
    """
    Send prompt to OpenRouter API; return list of titles or error messages.
    """
    if not OPENROUTER_API_KEY:
        current_app.logger.error("OpenRouter API key missing.")
        return [AI_MSG_OPENROUTER_KEY_MISSING]

    current_app.logger.debug(
        f"Sending prompt to AI (model={AI_MODEL_FOR_REQUESTS}, temp={temperature}):\n{prompt_content[:200]}..."
    )
    try:
        resp = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            data=json.dumps(
                {
                    "model": AI_MODEL_FOR_REQUESTS,
                    "messages": [{"role": "user", "content": prompt_content}],
                    "temperature": temperature,
                    "max_tokens": 150 if expected_responses > 1 else 50,
                }
            ),
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        if raw:
            if expected_responses == 1:
                if raw == "NO_CLEAR_MOVIE_TITLE_FOUND":
                    return ["NO_CLEAR_MOVIE_TITLE_FOUND"]
                cleaned = _clean_ai_single_movie_title_response(raw)
                current_app.logger.debug(f"AI single response: '{raw}' -> '{cleaned}'")
                return [cleaned] if cleaned else []
            titles = _clean_ai_movie_list_response(raw)
            current_app.logger.debug(f"AI list response: '{raw}' -> {titles}")
            return titles

        current_app.logger.warning("No content from AI.")
        return ([AI_MSG_NO_SUGGESTIONS_LIST] if expected_responses > 1 else [NO_CLEAR_MOVIE_TITLE_MARKER])

    except requests.exceptions.Timeout:
        current_app.logger.error("AI request timed out.")
        return [AI_MSG_REQUEST_TIMEOUT]
    except requests.exceptions.RequestException as err:
        current_app.logger.error(f"AI request exception: {err}.")
        user_err = AI_MSG_CONNECTION_ERROR_GENERIC
        if err.response is not None:
            try:
                detail = err.response.json().get("error", {}).get("message", str(err))
                user_err = AI_MSG_API_ERROR_DETAILED_TEMPLATE.format(error_message=detail)
            except ValueError:
                detail = f"{err.response.status_code} - {err.response.text[:100]}"
                user_err = AI_MSG_API_ERROR_DETAILED_TEMPLATE.format(error_message=detail)
        return [user_err]
    except Exception as err:
        current_app.logger.error(f"Generic AI error: {err}")
        return [AI_MSG_UNEXPECTED_ERROR_TEMPLATE.format(error_message=str(err))]


def _clean_ai_single_movie_title_response(raw_content: str) -> str:
    """
    Clean a single movie title from AI output.
    """
    title = raw_content.strip()
    m = re.search(r'"([^"]+)"', title)
    if m:
        title = m.group(1).strip()
    else:
        prefixes = [
            r"the most probable movie title is:?",
            r"it is likely:?",
            r"the movie title is:?",
            r"the movie is:?",
            r"movie title:?",
            r"movie:?",
            r"title:?",
            r"^\s*-\s*",
            r"^\s*\d+[,.\)]\s*",
        ]
        for p in prefixes:
            title = re.sub(f"^{p}", "", title, flags=re.IGNORECASE).strip()
        if (title.startswith('"') and title.endswith('"')) or (title.startswith("'") and title.endswith("'")):
            title = title[1:-1].strip()

    if title.endswith("."):
        title = title[:-1].strip()
    return title


def _clean_ai_movie_list_response(raw_content: str) -> list[str]:
    """
    Clean a newline-separated list of movie titles from AI output.
    """
    titles = []
    prefix_pattern = re.compile(r"^(\d+[,.)]?\s*|[-*•]+\s*)")
    lines = [line.strip() for line in raw_content.split("\n") if line.strip()]

    for line in lines:
        no_prefix = prefix_pattern.sub("", line).strip()
        if no_prefix:
            cleaned = _clean_ai_single_movie_title_response(no_prefix)
            if cleaned:
                titles.append(cleaned)
    return titles


if __name__ == "__main__":
    app.run(debug=True)
