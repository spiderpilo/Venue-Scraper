import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
DEFAULT_LOCATION = "Long Beach, CA"
DEFAULT_CATEGORY = "restaurants"
MAX_RESULTS = 5