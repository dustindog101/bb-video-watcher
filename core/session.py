"""
Session and Authentication Manager for bb-video-watcher.
Loads persistent session cookies from Blackboard Scraper cache and verifies authentication.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

DEFAULT_COOKIE_LOCATIONS = [
    Path("/Users/king/Desktop/school files/tools/blackboard-scraper/.session/cookies.json"),
    Path.home() / ".bb-scraper-session" / "cookies.json",
    Path.home() / ".blackboard-session" / "cookies.json",
]

BLACKBOARD_HOST = "blackboard.umbc.edu"
USER_ME_API = f"https://{BLACKBOARD_HOST}/learn/api/public/v1/users/me"


def find_cookie_file() -> Optional[Path]:
    """Find the first available cookies.json file from known locations."""
    for loc in DEFAULT_COOKIE_LOCATIONS:
        if loc.exists() and loc.stat().st_size > 10:
            return loc
    return None


def load_cookies() -> List[Dict[str, Any]]:
    """Load session cookies from the discovered cookies.json file."""
    cookie_file = find_cookie_file()
    if not cookie_file:
        raise FileNotFoundError(
            "No Blackboard session cookies found! "
            "Please run 'bb --login' in blackboard-scraper to authenticate first."
        )
    with open(cookie_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_cookie_header(cookies: Optional[List[Dict[str, Any]]] = None) -> str:
    """Format cookie list into an HTTP Cookie header string."""
    if cookies is None:
        cookies = load_cookies()
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if 'name' in c and 'value' in c)


def verify_session(cookies: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, Dict[str, Any]]:
    """
    Verify whether the cached session is active via Blackboard REST API.
    Returns (is_active, user_metadata_dict).
    """
    cookie_str = get_cookie_header(cookies)
    req = urllib.request.Request(USER_ME_API)
    req.add_header("Cookie", cookie_str)
    req.add_header("User-Agent", "Mozilla/5.0 (bb-video-watcher autonomous agent)")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return True, data
    except urllib.error.HTTPError as e:
        return False, {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return False, {"error": str(e)}

    return False, {"error": "Unexpected response"}
