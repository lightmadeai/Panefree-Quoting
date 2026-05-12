"""
Stable single-process Flask server for stress testing.
Threaded, no debug auto-reload, no use_reloader. Port 5001.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

import logging
logging.getLogger("werkzeug").setLevel(logging.WARNING)

from app import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, threaded=True, debug=False, use_reloader=False)
