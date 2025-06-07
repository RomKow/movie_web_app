"""
init_db.py

Initializes the database and creates all tables.
"""

import os

from dotenv import load_dotenv
from flask import Flask

from models import db

load_dotenv()


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URI', 'sqlite:///moviewebapp.db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def main():
    """Initialize the database tables."""
    app = create_app()
    with app.app_context():
        db.create_all()
        print("Database and tables created successfully.")


if __name__ == '__main__':
    main()
