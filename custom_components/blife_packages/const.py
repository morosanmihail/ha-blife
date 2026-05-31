"""Constants for the BLife Packages integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "blife_packages"

# Configuration keys
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_API_URL: Final = "api_url"

# API Configuration
AUTH_BASE_URL: Final = "https://auth.spikeglobal.io"
AUTH_LOGIN_PATH: Final = "/api/login-user"

DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=5)

# Sensor types
SENSOR_PACKAGES_COUNT: Final = "packages_ready_to_collect"

# Attributes
ATTR_PACKAGES: Final = "packages"
