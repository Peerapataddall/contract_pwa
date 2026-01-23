from __future__ import annotations

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

db = SQLAlchemy()
migrate = Migrate()

def create_app() -> Flask:
    load_dotenv()

    app = Flask(__name__, static_folder="static", template_folder="templates")

    database_url = os.getenv("DATABASE_URL") or "sqlite:///contract_pwa.db"
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-key"),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from .blueprints.pages import bp_pages
    from .blueprints.api import bp_api
    app.register_blueprint(bp_pages)
    app.register_blueprint(bp_api, url_prefix="/api")

    # ✅ Register Thai amount-to-text helper for Jinja
    from .utils import thai_baht_text
    app.jinja_env.globals["thai_baht_text"] = thai_baht_text
    app.jinja_env.filters["thai_baht_text"] = thai_baht_text

    # Ensure models are imported
    from . import models  # noqa: F401

    return app
