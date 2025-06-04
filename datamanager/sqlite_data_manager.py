# sqlite_data_manager.py
# Implements DataManagerInterface using SQLite/SQLAlchemy.

from datetime import datetime
from typing import List, Optional

from flask import current_app
from sqlalchemy import desc, func
from sqlalchemy.exc import SQLAlchemyError

from datamanager.data_manager_interface import DataManagerInterface
from models import Comment, Movie, User, UserMovie, db


class SQLiteDataManager(DataManagerInterface):
    """
    Concrete implementation of DataManagerInterface using SQLAlchemy with SQLite.
    Manages users, movies, ratings (UserMovie), and comments.
    """

    def get_all_users(self) -> List[User]:
        """
        Return a list of all users.
        """
        try:
            return User.query.all()
        except SQLAlchemyError as e:
            current_app.logger.error(f"Error fetching all users: {e}")
            return []

    def get_user_movies(self, user_id: int) -> List[Movie]:
        """
        Return all movies linked to the given user.
        """
        try:
            user = User.query.get(user_id)
            if not user:
                current_app.logger.warning(
                    f"User {user_id} not found when fetching movies"
                )
                return []
            return [link.movie for link in user.movies]
        except SQLAlchemyError as e:
            current_app.logger.error(f"Error fetching movies for user {user_id}: {e}")
            return []

    def add_user(self, name: str) -> Optional[User]:
        """
        Add a new user. Returns the User or None on failure.
        """
        name_clean = name.strip().lower()
        if not name_clean:
            current_app.logger.warning("Attempted to add user with empty name")
            return None

        try:
            exists = User.query.filter(func.lower(User.name) == name_clean).first()
            if exists:
                current_app.logger.warning(f"Duplicate user: '{name_clean}'")
                return None

            user = User(name=name_clean)
            db.session.add(user)
            db.session.commit()
            current_app.logger.info(f"User '{user.name}' added (ID: {user.id})")
            return user
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding user '{name_clean}': {e}")
            return None

    def _validate_movie_input(
        self, title: str, year: Optional[int], rating: Optional[float]
    ) -> bool:
        """
        Basic validation for movie title, year, and rating.
        """
        if not title:
            current_app.logger.warning("Validation failed: empty movie title")
            return False

        current_year = datetime.now().year
        if year is not None and year > current_year:
            current_app.logger.warning(
                f"Validation failed: year {year} > current year {current_year}"
            )
            return False

        if rating is not None and not (0 <= rating <= 5):
            current_app.logger.warning(
                f"Validation failed: rating {rating} not in 0-5"
            )
            return False

        return True

    def _get_or_create_movie_internal(
        self,
        title: str,
        director: Optional[str],
        year: Optional[int],
        poster_url: Optional[str],
        plot: Optional[str],
        runtime: Optional[str],
        awards: Optional[str],
        languages: Optional[str],
        genre: Optional[str],
        actors: Optional[str],
        writer: Optional[str],
        country: Optional[str],
        metascore: Optional[str],
        rated: Optional[str],
        imdb_id: Optional[str],
        omdb_data: Optional[dict],
    ) -> Optional[tuple[Movie, bool]]:
        """
        Find a movie by imdb_id or by title/year, or create it via omdb_data.
        Returns (Movie, was_created) or None.
        """
        try:
            if imdb_id:
                movie = Movie.query.filter_by(imdb_id=imdb_id).first()
                if movie:
                    current_app.logger.info(
                        f"Found movie by imdb_id '{imdb_id}' (ID: {movie.id})"
                    )
                    return movie, False

            movie = None
            if title and year is not None:
                movie = (
                    Movie.query.filter(
                        func.lower(Movie.title) == func.lower(title),
                        Movie.year == year,
                    )
                    .first()
                )
                if movie:
                    current_app.logger.info(
                        f"Found movie '{title}' ({year}) (ID: {movie.id})"
                    )
                    if imdb_id and not movie.imdb_id:
                        movie.imdb_id = imdb_id
                        db.session.commit()
                        current_app.logger.info(
                            f"Updated imdb_id for movie {movie.id} to '{imdb_id}'"
                        )
                    return movie, False

            if omdb_data:
                new_movie = self.add_movie_globally(omdb_data)
                if new_movie:
                    return new_movie, True
                current_app.logger.error(
                    f"Failed to create movie '{title}' via add_movie_globally"
                )
                return None

            current_app.logger.warning(
                f"Movie '{title}' not found and no OMDb data provided"
            )
            return None

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(
                f"SQLAlchemyError in _get_or_create_movie_internal for '{title}': {e}"
            )
            return None
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(
                f"Unexpected error in _get_or_create_movie_internal for '{title}': {e}"
            )
            return None

    def _create_or_update_user_movie_link(
        self, user_id: int, movie_id: int, rating: Optional[float]
    ) -> Optional[UserMovie]:
        """
        Create or update the UserMovie link for a user and movie.
        """
        try:
            link = UserMovie.query.filter_by(
                user_id=user_id, movie_id=movie_id
            ).first()
            if not link:
                link = UserMovie(user_id=user_id, movie_id=movie_id, user_rating=rating)
                db.session.add(link)
            else:
                if link.user_rating != rating:
                    link.user_rating = rating
                    db.session.add(link)
            return link
        except SQLAlchemyError as e:
            current_app.logger.error(
                f"Error creating/updating UserMovie link for user {user_id}, movie {movie_id}: {e}"
            )
            return None

    def add_movie(
        self,
        user_id: int,
        title: str,
        director: Optional[str],
        year: Optional[int],
        rating: Optional[float],
        poster_url: Optional[str] = None,
        plot: Optional[str] = None,
        runtime: Optional[str] = None,
        awards: Optional[str] = None,
        languages: Optional[str] = None,
        genre: Optional[str] = None,
        actors: Optional[str] = None,
        writer: Optional[str] = None,
        country: Optional[str] = None,
        metascore: Optional[str] = None,
        rated: Optional[str] = None,
        imdb_id: Optional[str] = None,
        omdb_rating_for_community: Optional[float] = None,
    ) -> Optional[Movie]:
        """
        Add a movie to a user's list. Creates the movie globally if needed.
        Returns the Movie or None on failure.
        """
        title_clean = title.strip() if title else ""
        if not self._validate_movie_input(title_clean, year, rating):
            return None

        try:
            user = self.get_user_by_id(user_id)
            if not user:
                current_app.logger.warning(f"User {user_id} not found")
                return None

            omdb_payload = None
            if imdb_id:
                omdb_payload = {
                    "Title": title_clean,
                    "Director": director,
                    "Year": str(year) if year else None,
                    "Poster": poster_url,
                    "Plot": plot,
                    "Runtime": runtime,
                    "Awards": awards,
                    "Language": languages,
                    "Genre": genre,
                    "Actors": actors,
                    "Writer": writer,
                    "Country": country,
                    "Metascore": metascore,
                    "Rated": rated,
                    "imdbID": imdb_id,
                    "imdbRating": str(omdb_rating_for_community * 2)
                    if omdb_rating_for_community is not None
                    else None,
                }

            result = self._get_or_create_movie_internal(
                title_clean,
                director,
                year,
                poster_url,
                plot,
                runtime,
                awards,
                languages,
                genre,
                actors,
                writer,
                country,
                metascore,
                rated,
                imdb_id,
                omdb_data=omdb_payload,
            )
            if not result:
                raise SQLAlchemyError("Failed to get or create movie internally")

            movie_obj, _ = result
            link = self._create_or_update_user_movie_link(
                user.id, movie_obj.id, rating
            )
            if not link:
                raise SQLAlchemyError(
                    f"Failed to link user {user.id} with movie {movie_obj.id}"
                )

            db.session.commit()
            current_app.logger.info(
                f"Committed changes for movie {movie_obj.id} and user {user_id}"
            )

            if self._update_community_rating(movie_obj.id):
                return movie_obj
            current_app.logger.error(
                f"Community rating update failed for movie {movie_obj.id}"
            )
            return movie_obj

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Error in add_movie: {e}")
            return None
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Unexpected error in add_movie: {e}")
            return None

    def update_user_rating_for_movie(
        self, user_id: int, movie_id: int, new_rating: Optional[float]
    ) -> bool:
        """
        Update a user's rating for a movie. Returns True on success.
        """
        try:
            link = UserMovie.query.filter_by(
                user_id=user_id, movie_id=movie_id
            ).first()
            if not link:
                current_app.logger.warning(
                    f"No UserMovie link for user {user_id}, movie {movie_id}"
                )
                return False

            if new_rating is not None and not (0 <= new_rating <= 5):
                current_app.logger.warning(
                    f"Invalid rating {new_rating} for user {user_id}, movie {movie_id}"
                )
                return False

            link.user_rating = new_rating
            db.session.commit()
            current_app.logger.info(
                f"User {user_id} rating for movie {movie_id} set to {new_rating}"
            )

            return self._update_community_rating(movie_id)

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(
                f"Error updating rating for user {user_id}, movie {movie_id}: {e}"
            )
            return False

    def delete_movie(self, movie_id: int) -> bool:
        """
        Delete a movie globally by its ID (cascades to UserMovie and Comment).
        """
        try:
            movie = Movie.query.get(movie_id)
            if not movie:
                current_app.logger.warning(f"Movie {movie_id} not found for deletion")
                return False

            db.session.delete(movie)
            db.session.commit()
            current_app.logger.info(f"Deleted movie {movie_id} globally")
            return True

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting movie {movie_id}: {e}")
            return False

    def add_existing_movie_to_user_list(self, user_id: int, movie_id: int) -> bool:
        """
        Add an existing movie to a user's list (no initial rating).
        """
        try:
            user = User.query.get(user_id)
            if not user:
                current_app.logger.warning(f"User {user_id} not found")
                return False

            movie = Movie.query.get(movie_id)
            if not movie:
                current_app.logger.warning(f"Movie {movie_id} not found")
                return False

            exists = UserMovie.query.filter_by(
                user_id=user_id, movie_id=movie_id
            ).first()
            if exists:
                current_app.logger.info(
                    f"Movie {movie_id} already in user {user_id}'s list"
                )
                return True

            link = UserMovie(user_id=user.id, movie_id=movie.id, user_rating=None)
            db.session.add(link)
            db.session.commit()
            current_app.logger.info(
                f"Added movie {movie_id} to user {user_id} list"
            )

            return self._update_community_rating(movie_id)

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(
                f"Error adding movie {movie_id} to user {user_id}: {e}"
            )
            return False

    def _update_community_rating(self, movie_id: int) -> bool:
        """
        Recalculate and update a movie's community rating and rating count.
        """
        try:
            movie = Movie.query.get(movie_id)
            if not movie:
                current_app.logger.warning(
                    f"Movie {movie_id} not found for community update"
                )
                return False

            total = 0.0
            count = 0

            if movie.initial_omdb_rating is not None:
                total += movie.initial_omdb_rating
                count += 1
                current_app.logger.debug(
                    f"Including initial OMDb rating {movie.initial_omdb_rating}"
                )

            ratings = (
                db.session.query(UserMovie.user_rating)
                .filter(
                    UserMovie.movie_id == movie_id,
                    UserMovie.user_rating.isnot(None),
                )
                .all()
            )
            user_values = [r[0] for r in ratings]
            total += sum(user_values)
            count += len(user_values)

            if count > 0:
                movie.community_rating = round(total / count, 2)
                movie.community_rating_count = count
            else:
                movie.community_rating = None
                movie.community_rating_count = 0

            db.session.commit()
            current_app.logger.info(
                f"Updated community rating for movie {movie_id} to "
                f"{movie.community_rating} ({movie.community_rating_count} ratings)"
            )
            return True

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(
                f"Error updating community rating for movie {movie_id}: {e}"
            )
            return False

    def delete_movie_from_user_list(self, user_id: int, movie_id: int) -> bool:
        """
        Remove a movie from a user's list by deleting the UserMovie link.
        """
        try:
            link = UserMovie.query.filter_by(
                user_id=user_id, movie_id=movie_id
            ).first()
            if not link:
                current_app.logger.warning(
                    f"No UserMovie link to delete for user {user_id}, movie {movie_id}"
                )
                return False

            db.session.delete(link)
            db.session.commit()
            current_app.logger.info(
                f"Removed movie {movie_id} from user {user_id}'s list"
            )

            return self._update_community_rating(movie_id)

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(
                f"Error removing movie {movie_id} from user {user_id}: {e}"
            )
            return False

    def get_movie_by_imdb_id(self, imdb_id: str) -> Optional[Movie]:
        """
        Return a movie by its IMDb ID.
        """
        if not imdb_id:
            current_app.logger.debug("Empty imdb_id provided")
            return None
        try:
            return Movie.query.filter_by(imdb_id=imdb_id).first()
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Error fetching movie by imdb_id '{imdb_id}': {e}")
            return None

    def _parse_omdb_data_for_movie_fields(self, movie_data: dict) -> dict:
        """
        Convert raw OMDb-like data into a dict for Movie model.
        """
        parsed = {}
        imdb_id = movie_data.get("imdbID", "N/A")

        parsed["title"] = movie_data.get("Title", "N/A").strip()
        parsed["director"] = movie_data.get("Director", "").strip() or None
        parsed["plot"] = movie_data.get("Plot", "").strip() or None
        parsed["runtime"] = movie_data.get("Runtime", "").strip() or None
        parsed["awards"] = movie_data.get("Awards", "").strip() or None
        parsed["language"] = movie_data.get("Language", "").strip() or None
        parsed["genre"] = movie_data.get("Genre", "").strip() or None
        parsed["actors"] = movie_data.get("Actors", "").strip() or None
        parsed["writer"] = movie_data.get("Writer", "").strip() or None
        parsed["country"] = movie_data.get("Country", "").strip() or None
        parsed["metascore"] = movie_data.get("Metascore", "").strip() or None
        parsed["rated_omdb"] = movie_data.get("Rated", "").strip() or None
        parsed["imdb_id"] = imdb_id

        year_str = movie_data.get("Year", "").strip()
        year = None
        if year_str:
            year_part = year_str.split("–")[0].split("-")[0].strip()
            if year_part.isdigit():
                year = int(year_part)
            else:
                current_app.logger.warning(
                    f"Invalid year '{year_str}' for imdbID {imdb_id}"
                )
        parsed["year"] = year

        poster = movie_data.get("Poster")
        parsed["poster_url"] = poster if poster and poster != "N/A" else None

        raw_rating = movie_data.get("imdbRating")
        initial = None
        if raw_rating and raw_rating != "N/A":
            try:
                r10 = float(raw_rating)
                r5 = round(r10 / 2, 1)
                if 0 <= r5 <= 5:
                    initial = r5
                else:
                    current_app.logger.warning(
                        f"Converted rating {r5} out of range for imdbID {imdb_id}"
                    )
            except ValueError:
                current_app.logger.warning(
                    f"Invalid imdbRating '{raw_rating}' for imdbID {imdb_id}"
                )
        parsed["initial_omdb_rating"] = initial

        return parsed

    def add_movie_globally(self, movie_data: dict) -> Optional[Movie]:
        """
        Add a movie globally using OMDb data. Returns the Movie or None.
        """
        raw_id = movie_data.get("imdbID")
        if not raw_id:
            current_app.logger.warning("No imdbID in OMDb data")
            return None

        try:
            exist = Movie.query.filter_by(imdb_id=raw_id).first()
            if exist:
                current_app.logger.info(
                    f"Movie with imdb_id {raw_id} exists (ID: {exist.id})"
                )
                return exist

            fields = self._parse_omdb_data_for_movie_fields(movie_data)
            if not fields.get("imdb_id"):
                current_app.logger.error(
                    f"imdbID missing after parsing for raw_id {raw_id}"
                )
                return None

            new_movie = Movie(**fields)
            db.session.add(new_movie)
            db.session.flush()

            if self._update_community_rating(new_movie.id):
                return new_movie

            db.session.rollback()
            current_app.logger.error(
                f"Community update failed for new movie {new_movie.id}"
            )
            return None

        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Error in add_movie_globally: {e}")
            return None

    def get_top_movies(self, limit: int = 10) -> List[tuple[Movie, int, Optional[float]]]:
        """
        Return top movies by user count and community rating.
        """
        try:
            results = (
                db.session.query(
                    Movie,
                    func.count(UserMovie.user_id).label("user_count"),
                    Movie.community_rating,
                )
                .join(UserMovie, UserMovie.movie_id == Movie.id)
                .group_by(Movie.id, Movie.community_rating)
                .order_by(desc("user_count"), desc(Movie.community_rating))
                .limit(limit)
                .all()
            )
            return results
        except SQLAlchemyError as e:
            current_app.logger.error(f"Error fetching top movies: {e}")
            return []

    def get_user_by_name(self, name: str) -> Optional[User]:
        """
        Return a user by name (case-insensitive).
        """
        search = name.strip().lower()
        if not search:
            current_app.logger.debug("Empty name provided for get_user_by_name")
            return None
        try:
            return User.query.filter(func.lower(User.name) == search).first()
        except SQLAlchemyError as e:
            current_app.logger.error(f"Error fetching user by name '{search}': {e}")
            return None

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Return a user by their ID.
        """
        if not isinstance(user_id, int):
            current_app.logger.warning(f"Non-integer user_id: {user_id}")
            return None
        try:
            return User.query.get(user_id)
        except SQLAlchemyError as e:
            current_app.logger.error(f"Error fetching user by ID {user_id}: {e}")
            return None

    def get_user_movie_relations(self, user_id: int) -> List[UserMovie]:
        """
        Return all UserMovie links for the given user.
        """
        try:
            user = self.get_user_by_id(user_id)
            if not user:
                current_app.logger.warning(
                    f"User {user_id} not found for movie relations"
                )
                return []

            return (
                UserMovie.query.filter_by(user_id=user_id)
                .join(Movie)
                .order_by(Movie.id)
                .all()
            )
        except SQLAlchemyError as e:
            current_app.logger.error(
                f"Error fetching UserMovie relations for user {user_id}: {e}"
            )
            return []

    def get_movie_by_id(self, movie_id: int) -> Optional[Movie]:
        """
        Return a movie by its ID.
        """
        if not isinstance(movie_id, int):
            current_app.logger.warning(f"Non-integer movie_id: {movie_id}")
            return None
        try:
            return Movie.query.get(movie_id)
        except SQLAlchemyError as e:
            current_app.logger.error(f"Error fetching movie by ID {movie_id}: {e}")
            return None

    def add_comment(self, movie_id: int, user_id: int, text: str) -> Optional[Comment]:
        """
        Add a comment to a movie by a user. Returns the Comment or None.
        """
        text_clean = text.strip()
        if not text_clean:
            current_app.logger.warning("Attempted to add empty comment")
            return None

        user = self.get_user_by_id(user_id)
        if not user:
            current_app.logger.warning(f"User {user_id} not found for comment")
            return None

        movie = self.get_movie_by_id(movie_id)
        if not movie:
            current_app.logger.warning(f"Movie {movie_id} not found for comment")
            return None

        try:
            comment = Comment(movie_id=movie.id, user_id=user.id, text=text_clean)
            db.session.add(comment)
            db.session.commit()
            current_app.logger.info(
                f"Added comment {comment.id} by user {user_id} to movie {movie_id}"
            )
            return comment
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(
                f"Error adding comment for user {user_id}, movie {movie_id}: {e}"
            )
            return None

    def get_all_movies(self) -> List[Movie]:
        """
        Return all movies ordered by title.
        """
        try:
            return Movie.query.order_by(Movie.title).all()
        except SQLAlchemyError as e:
            current_app.logger.error(f"Error fetching all movies: {e}")
            return []

    def get_comments_for_movie(self, movie_id: int) -> List[Comment]:
        """
        Return all comments for a movie, newest first.
        """
        movie = self.get_movie_by_id(movie_id)
        if not movie:
            current_app.logger.warning(f"Movie {movie_id} not found for comments")
            return []
        try:
            return (
                Comment.query.filter_by(movie_id=movie_id)
                .order_by(Comment.created_at.desc())
                .all()
            )
        except SQLAlchemyError as e:
            current_app.logger.error(
                f"Error fetching comments for movie {movie_id}: {e}"
            )
            return []

    def get_user_movie_link(self, user_id: int, movie_id: int) -> Optional[UserMovie]:
        """
        Return the UserMovie link between a user and movie.
        """
        user = self.get_user_by_id(user_id)
        if not user:
            current_app.logger.warning(f"User {user_id} not found for link fetch")
            return None

        movie = self.get_movie_by_id(movie_id)
        if not movie:
            current_app.logger.warning(f"Movie {movie_id} not found for link fetch")
            return None

        try:
            return UserMovie.query.filter_by(
                user_id=user_id, movie_id=movie_id
            ).first()
        except SQLAlchemyError as e:
            current_app.logger.error(
                f"Error fetching UserMovie link for user {user_id}, movie {movie_id}: {e}"
            )
            return None
