import os
from dotenv import load_dotenv

# Load .env file if present (local development)
load_dotenv()

from app import app  # noqa: F401

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
    app.run(host="0.0.0.0", port=5000, debug=debug)
