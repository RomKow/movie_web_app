"""
models.py

Defines SQLAlchemy ORM models for CineCrowd:
- User: application users
- Movie: movie metadata
- UserMovie: many-to-many link with user-specific rating
- Comment: user comments on movies
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

# Global SQLAlchemy instance (initialized in app.py)
db = SQLAlchemy()


class User(db.Model):
    """
    A user of MovieWeb.

    Attributes:
        id (int): Unique user identifier.
        name (str): Unique username.
        movies (list[UserMovie]): Movies in the user's list.
        comments (list[Comment]): Comments made by the user.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    movies = db.relationship(
        "UserMovie", back_populates="user", cascade="all, delete-orphan"
    )
    comments = db.relationship(
        "Comment", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User {self.id} {self.name}>"


class Movie(db.Model):
    """
    A film with metadata and community ratings.

    Attributes:
        id (int): Unique movie identifier.
        title (str): Movie title.
        original_title (str | None): Original title if different.
        director (str | None): Director name.
        writer (str | None): Writer(s).
        actors (str | None): Lead actors.
        year (int | None): Release year.
        runtime (str | None): Duration string.
        genre (str | None): Genre(s).
        plot (str | None): Plot summary.
        language (str | None): Language(s).
        country (str | None): Production country.
        awards (str | None): Awards summary.
        poster_url (str | None): URL to poster image.
        community_rating (float | None): Average user rating.
        community_rating_count (int): Number of ratings.
        imdb_id (str | None): IMDb identifier.
        metascore (str | None): Metascore value.
        rated_omdb (str | None): MPAA rating from OMDb.
        initial_omdb_rating (float | None): Imported OMDb rating.
        users (list[UserMovie]): Users who have this movie.
        comments (list[Comment]): Comments on this movie.
    """
    __tablename__ = "movies"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    original_title = db.Column(db.String(255))
    director = db.Column(db.String(255))
    writer = db.Column(db.Text)
    actors = db.Column(db.Text)
    year = db.Column(db.Integer)
    runtime = db.Column(db.String(50))
    genre = db.Column(db.String(255))
    plot = db.Column(db.Text)
    language = db.Column(db.String(255))
    country = db.Column(db.String(255))
    awards = db.Column(db.Text)
    poster_url = db.Column(db.String(255))
    community_rating = db.Column(db.Float)
    community_rating_count = db.Column(db.Integer, default=0)
    imdb_id = db.Column(db.String(20), unique=True)
    metascore = db.Column(db.String(10))
    rated_omdb = db.Column(db.String(20))
    initial_omdb_rating = db.Column(db.Float)

    users = db.relationship(
        "UserMovie", back_populates="movie", cascade="all, delete-orphan"
    )
    comments = db.relationship(
        "Comment", back_populates="movie", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Movie {self.id} {self.title}>"


class UserMovie(db.Model):
    """
    Association between User and Movie with a personal rating.

    Attributes:
        id (int): Unique identifier for this link.
        user_id (int): ID of the user.
        movie_id (int): ID of the movie.
        user_rating (float | None): User's rating (0–5).
        user (User): The associated user.
        movie (Movie): The associated movie.
    """
    __tablename__ = "user_movies"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey("movies.id"), nullable=False)
    user_rating = db.Column(db.Float)

    user = db.relationship("User", back_populates="movies")
    movie = db.relationship("Movie", back_populates="users")

    def __repr__(self):
        return f"<UserMovie user={self.user_id} movie={self.movie_id}>"


class Comment(db.Model):
    """
    A comment made by a user on a movie.

    Attributes:
        id (int): Unique comment identifier.
        text (str): Comment content.
        created_at (datetime): Timestamp of creation.
        likes_count (int): Number of likes (future feature).
        user_id (int): ID of the commenter.
        movie_id (int): ID of the commented movie.
        user (User): The commenting user.
        movie (Movie): The movie commented on.
    """
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    likes_count = db.Column(db.Integer, default=0, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey("movies.id"), nullable=False)

    user = db.relationship("User", back_populates="comments")
    movie = db.relationship("Movie", back_populates="comments")

    def __repr__(self):
        return f"<Comment {self.id} user={self.user_id} movie={self.movie_id}>"
