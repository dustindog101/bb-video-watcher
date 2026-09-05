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

LOCAL_SESSION_DIR = Path(__file__).resolve().parent.parent / ".session"
LOCAL_COOKIE_FILE = LOCAL_SESSION_DIR / "cookies.json"

DEFAULT_COOKIE_LOCATIONS = [
    LOCAL_COOKIE_FILE,
    Path("/Users/king/Desktop/school files/tools/blackboard-scraper/.session/cookies.json"),
    Path.home() / ".bb-scraper-session" / "cookies.json",
    Path.home() / ".blackboard-session" / "cookies.json",
]

BLACKBOARD_HOST = "blackboard.umbc.edu"
USER_ME_API = f"https://{BLACKBOARD_HOST}/learn/api/public/v1/users/me"


def sanitize_playwright_cookies(raw_cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw cookies to valid Playwright format, resolving sameSite and required fields."""
    clean = []
    for c in raw_cookies:
        if not c.get("name") or not c.get("value"):
            continue
        domain = c.get("domain") or "blackboard.umbc.edu"
        path = c.get("path") or "/"
        cookie = {
            "name": str(c["name"]),
            "value": str(c["value"]),
            "domain": str(domain),
            "path": str(path),
        }
        if "secure" in c:
            cookie["secure"] = bool(c["secure"])
        if "httpOnly" in c:
            cookie["httpOnly"] = bool(c["httpOnly"])
        
        # Handle sameSite strictly for Chrome/Playwright standards
        ss = str(c.get("sameSite", "")).lower()
        if ss == "strict":
            cookie["sameSite"] = "Strict"
        elif ss == "lax":
            cookie["sameSite"] = "Lax"
        elif ss in ("none", "no_restriction"):
            cookie["sameSite"] = "None"
            cookie["secure"] = True  # Chrome requires secure=True when sameSite=None
            
        if "expires" in c and isinstance(c["expires"], (int, float)) and c["expires"] > 0:
            cookie["expires"] = float(c["expires"])
            
        clean.append(cookie)
    return clean


def auto_sync_session_from_external() -> Optional[Path]:
    """Check external sources (e.g. blackboard-scraper) and auto-transfer new cookies into local cache."""
    external_locations = [
        Path("/Users/king/Desktop/school files/tools/blackboard-scraper/.session/cookies.json"),
        Path.home() / ".bb-scraper-session" / "cookies.json",
        Path.home() / ".blackboard-session" / "cookies.json",
    ]
    for ext in external_locations:
        if ext.exists() and ext.stat().st_size > 10:
            try:
                # If local doesn't exist or external is newer, transfer
                if not LOCAL_COOKIE_FILE.exists() or ext.stat().st_mtime > LOCAL_COOKIE_FILE.stat().st_mtime:
                    LOCAL_SESSION_DIR.mkdir(parents=True, exist_ok=True)
                    with open(ext, "r", encoding="utf-8") as src_f:
                        data = json.load(src_f)
                    with open(LOCAL_COOKIE_FILE, "w", encoding="utf-8") as dst_f:
                        json.dump(data, dst_f, indent=2)
                    return LOCAL_COOKIE_FILE
            except Exception:
                pass
    return None


def find_cookie_file() -> Optional[Path]:
    """Find the first available cookies.json file from known locations, auto-syncing if possible."""
    auto_sync_session_from_external()
    for loc in DEFAULT_COOKIE_LOCATIONS:
        if loc.exists() and loc.stat().st_size > 10:
            return loc
    return None


def load_cookies(for_playwright: bool = False) -> List[Dict[str, Any]]:
    """Load session cookies from the discovered cookies.json file."""
    cookie_file = find_cookie_file()
    if not cookie_file:
        raise FileNotFoundError(
            "No Blackboard session cookies found! "
            "Please run 'bb --login' in blackboard-scraper to authenticate first."
        )
    with open(cookie_file, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    if for_playwright:
        return sanitize_playwright_cookies(cookies)
    return cookies


def get_cookie_header(cookies: Optional[List[Dict[str, Any]]] = None) -> str:
    """Format cookie list into an HTTP Cookie header string."""
    if cookies is None:
        try:
            cookies = load_cookies()
        except Exception:
            return ""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if 'name' in c and 'value' in c)


def verify_session(cookies: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, Dict[str, Any]]:
    """
    Verify whether the cached session is active via Blackboard REST API.
    Returns (is_active, user_metadata_dict).
    """
    cookie_str = get_cookie_header(cookies)
    if not cookie_str:
        return False, {"error": "No cookies available"}

    req = urllib.request.Request(USER_ME_API)
    req.add_header("Cookie", cookie_str)
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")

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
