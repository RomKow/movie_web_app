# data_manager_interface.py
# Defines the interface for DataManager implementations.

from abc import ABC, abstractmethod
from models import Comment, Movie, User, UserMovie
from typing import List, Optional


class DataManagerInterface(ABC):
    """
    Abstract interface for data access operations.
    """

    @abstractmethod
    def get_all_users(self) -> List[User]:
        """
        Return a list of all users.
        """
        pass

    @abstractmethod
    def get_user_movies(self, user_id: int) -> List[Movie]:
        """
        Return all movies for a given user.
        """
        pass

    @abstractmethod
    def add_user(self, name: str) -> Optional[User]:
        """
        Add a new user and return the User object.
        """
        pass

    @abstractmethod
    def add_movie(
        self,
        user_id: int,
        title: str,
        director: str,
        year: int,
        rating: float,
        poster_url: Optional[str] = None,
    ) -> Optional[Movie]:
        """
        Add a new movie for the specified user.
        """
        pass

    @abstractmethod
    def update_user_rating_for_movie(
        self,
        user_id: int,
        movie_id: int,
        new_rating: Optional[float],
    ) -> bool:
        """
        Update the user's rating for a movie.
        Use None to remove an existing rating.
        """
        pass

    @abstractmethod
    def delete_movie(self, movie_id: int) -> bool:
        """
        Delete a movie by its ID.
        """
        pass

    @abstractmethod
    def get_top_movies(
        self, limit: int = 10
    ) -> List[tuple[Movie, int, Optional[float]]]:
        """
        Return top movies by user count and average rating.
        Each tuple: (Movie, user_count, average_rating).
        """
        pass

    @abstractmethod
    def get_user_by_name(self, name: str) -> Optional[User]:
        """
        Return a user by name (case-insensitive).
        """
        pass

    @abstractmethod
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Return a user by their ID.
        """
        pass

    @abstractmethod
    def get_user_movie_relations(self, user_id: int) -> List[UserMovie]:
        """
        Return all UserMovie relations for the given user.
        """
        pass

    @abstractmethod
    def get_movie_by_id(self, movie_id: int) -> Optional[Movie]:
        """
        Return a movie by its ID.
        """
        pass

    @abstractmethod
    def add_comment(self, movie_id: int, user_id: int, text: str) -> Optional[Comment]:
        """
        Add a new comment to a movie.
        """
        pass

    @abstractmethod
    def get_all_movies(self) -> List[Movie]:
        """
        Return all movies in the database.
        """
        pass

    @abstractmethod
    def get_comments_for_movie(self, movie_id: int) -> List[Comment]:
        """
        Return all comments for a movie, newest first.
        """
        pass

    @abstractmethod
    def get_user_movie_link(
        self, user_id: int, movie_id: int
    ) -> Optional[UserMovie]:
        """
        Return the UserMovie link between a user and a movie.
        """
        pass
