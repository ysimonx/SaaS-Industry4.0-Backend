"""
Flask extensions initialization.

Extensions are initialized here and then imported in the application factory.
This prevents circular imports and allows for proper configuration.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import redis
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

# Initialize extensions
# These will be initialized with the Flask app in the application factory
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()


class RedisManager:
    """Manager for Redis connections"""

    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self.enabled: bool = False

    def init_app(self, app):
        """Initialize Redis connection with Flask app configuration"""
        redis_url = app.config.get('REDIS_URL') or os.getenv('REDIS_URL')

        if redis_url:
            try:
                # Parse Redis URL and create connection pool
                max_connections = int(app.config.get('REDIS_MAX_CONNECTIONS', 20))
                decode_responses = app.config.get('REDIS_DECODE_RESPONSES', True)

                self.client = redis.from_url(
                    redis_url,
                    max_connections=max_connections,
                    decode_responses=decode_responses,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30
                )

                # Test the connection
                self.client.ping()
                self.enabled = True
                logger.info(f"Redis connected successfully at {redis_url}")

            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Running without Redis.")
                self.client = None
                self.enabled = False
        else:
            logger.info("Redis URL not configured. Running without Redis.")
            self.enabled = False

    def get_client(self) -> Optional[redis.Redis]:
        """Get Redis client if available"""
        return self.client if self.enabled else None

    def is_enabled(self) -> bool:
        """Check if Redis is enabled and connected"""
        if not self.enabled or not self.client:
            return False
        try:
            self.client.ping()
            return True
        except:
            return False


# Initialize Redis manager
redis_manager = RedisManager()
