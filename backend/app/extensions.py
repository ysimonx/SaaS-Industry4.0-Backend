"""
Flask extensions initialization.

Extensions are initialized here and then imported in the application factory.
This prevents circular imports and allows for proper configuration.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS

# Initialize extensions
# These will be initialized with the Flask app in the application factory
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
