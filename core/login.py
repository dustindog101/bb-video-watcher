"""
Autonomous and Interactive Login Manager for bb-video-watcher.
Handles UMBC SSO authentication, Duo 2FA with macOS SMS capture,
and stores session cookies directly in .session/cookies.json.
"""

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    sync_playwright = None

from core.session import (
    LOCAL_SESSION_DIR,
    LOCAL_COOKIE_FILE,
    sanitize_playwright_cookies,
    verify_session,
    BLACKBOARD_HOST
)

LOCAL_CONFIG_FILE = LOCAL_SESSION_DIR / "config.json"
SSO_URL = f"https://{BLACKBOARD_HOST}/ultra/course"


def get_stored_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Load stored credentials from .session/config.json or legacy config."""
    if LOCAL_CONFIG_FILE.exists():
        try:
            with open(LOCAL_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                auto = data.get("auto_login", {})
                if auto.get("username") and auto.get("password"):
                    return auto["username"], auto["password"]
        except Exception:
            pass

    # Check external project config as fallback
    scraper_cfg = Path("/Users/king/Desktop/school files/tools/blackboard-scraper/config.json")
    if scraper_cfg.exists():
        try:
            with open(scraper_cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
                auto = data.get("auto_login", {})
                if auto.get("username") and auto.get("password"):
                    return auto["username"], auto["password"]
        except Exception:
            pass

    return None, None


def save_stored_credentials(username: str, password: str) -> None:
    """Save credentials to local .session/config.json."""
    LOCAL_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    if LOCAL_CONFIG_FILE.exists():
        try:
            with open(LOCAL_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data["auto_login"] = {"username": username.strip(), "password": password}
    with open(LOCAL_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_current_max_sms_rowid() -> int:
    """Get latest message rowid in macOS Messages chat.db."""
    if sys.platform != "darwin":
        return 0
    db_path = Path.home() / "Library" / "Messages" / "chat.db"
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
        c = conn.cursor()
        c.execute("SELECT MAX(ROWID) FROM message")
        res = c.fetchone()
        conn.close()
        return res[0] if res and res[0] is not None else 0
    except Exception:
        return 0


def extract_duo_sms_passcode(start_rowid: int = 0, timeout_seconds: int = 45) -> Optional[str]:
    """Poll macOS Messages for Duo or UMBC verification code."""
    if sys.platform != "darwin":
        return None
    db_path = Path.home() / "Library" / "Messages" / "chat.db"
    if not db_path.exists():
        return None

    patterns = [
        re.compile(r"UMBC\s+SMS\s+passcode.*?:\s*(\d{6,8})", re.I),
        re.compile(r"Duo\s+passcode.*?:\s*(\d{6,8})", re.I),
        re.compile(r"passcode\s+(\d{6,8})\s+to\s+log\s+in", re.I),
        re.compile(r"(?:code|passcode)\s+is[:\s]+(\d{6,8})", re.I),
        re.compile(r"\b(\d{6,7})\b"),
    ]

    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1.0)
            c = conn.cursor()
            c.execute(
                "SELECT ROWID, text FROM message WHERE ROWID > ? AND text IS NOT NULL ORDER BY ROWID DESC LIMIT 10",
                (start_rowid,)
            )
            rows = c.fetchall()
            conn.close()

            for rowid, text in rows:
                if not text:
                    continue
                for pat in patterns:
                    m = pat.search(text)
                    if m:
                        return m.group(1).strip()
        except Exception:
            pass
        time.sleep(1.0)
    return None


def perform_login(
    username: Optional[str] = None,
    password: Optional[str] = None,
    headless: bool = True,
    auto_sms: bool = True,
    force: bool = False
) -> Tuple[bool, Dict[str, Any]]:
    """
    Standalone login runner for bb-video-watcher.
    Authenticates via SSO, extracts Duo 2FA, and saves cookies locally.
    """
    if sync_playwright is None:
        return False, {"error": "Playwright is not installed"}

    usr = username
    pwd = password
    if not usr or not pwd:
        stored_u, stored_p = get_stored_credentials()
        usr = usr or stored_u
        pwd = pwd or stored_p

    if not usr or not pwd:
        return False, {"error": "No credentials provided. Run 'bb-video-watcher login -u USER -p PASS' or save to config."}

    LOCAL_SESSION_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = None
        for ch in ["chrome", "msedge", "chromium", None]:
            try:
                kw = {
                    "headless": headless,
                    "args": ["--disable-blink-features=AutomationControlled", "--no-first-run"]
                }
                if ch:
                    kw["channel"] = ch
                browser = p.chromium.launch(**kw)
                break
            except Exception:
                continue

        if not browser:
            return False, {"error": "Could not launch Chrome browser"}

        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")

        if force:
            context.clear_cookies()

        page = context.new_page()

        try:
            print(f"🔑 Initiating login for user '{usr}'...")
            page.goto(SSO_URL, timeout=40000)
            page.wait_for_timeout(2500)

            # 1. Check if login portal button is visible
            for btn_text in ["Log into Blackboard via myUMBC", "UMBC Login", "Sign in"]:
                try:
                    btn = page.get_by_text(btn_text, exact=True)
                    if btn.is_visible(timeout=1500):
                        btn.click()
                        page.wait_for_timeout(2000)
                        break
                except Exception:
                    pass

            # 2. Fill credentials
            try:
                usr_field = page.locator("input[type='text'], input[type='email'], input[name='j_username']").first
                if usr_field.is_visible(timeout=5000):
                    usr_field.fill(usr)
                pwd_field = page.locator("input[type='password'], input[name='j_password']").first
                if pwd_field.is_visible(timeout=3000):
                    pwd_field.fill(pwd)
                    pwd_field.press("Enter")
                    page.wait_for_timeout(2500)
            except Exception as e:
                print(f"   ⚠️ Notice during credential fill: {e}")

            # 3. Handle Duo 2FA
            duo_active = False
            for _ in range(15):
                cur_url = page.url.lower()
                if "duosecurity.com" in cur_url:
                    duo_active = True
                    break
                if "blackboard.umbc.edu/ultra" in cur_url:
                    break
                page.wait_for_timeout(500)

            if duo_active:
                print("📱 Handling Duo 2FA...")
                start_rowid = get_current_max_sms_rowid()

                # Click Other options
                try:
                    other_btn = page.get_by_text("Other options", exact=False).first
                    if other_btn.is_visible(timeout=3000):
                        other_btn.click()
                        page.wait_for_timeout(1500)
                except Exception:
                    pass

                # Click Text message passcode
                try:
                    sms_opt = page.get_by_text("Text message passcode", exact=False).first
                    if sms_opt.is_visible(timeout=4000):
                        sms_opt.click()
                        page.wait_for_timeout(2000)
                except Exception:
                    pass

                # Extract SMS passcode
                passcode = None
                if auto_sms and sys.platform == "darwin":
                    print("   ↳ Listening for incoming SMS passcode...")
                    passcode = extract_duo_sms_passcode(start_rowid=start_rowid, timeout_seconds=30)

                if not passcode:
                    if sys.stdin.isatty():
                        try:
                            passcode = input("   ↳ Enter 6-digit Duo Passcode from your phone: ").strip()
                        except Exception:
                            passcode = None

                if passcode:
                    print(f"   ↳ Submitting Duo Passcode: {passcode}")
                    p_input = page.locator("input[name='passcode'], input[id*='passcode'], input[type='text'][autocomplete]").first
                    if p_input.is_visible(timeout=5000):
                        p_input.fill(passcode)
                        p_input.press("Enter")
                        page.wait_for_timeout(3000)

                # Check "Remember me for 30 days" if present
                try:
                    trust_btn = page.get_by_role("button", name=re.compile(r"yes.*this.*device|trust", re.I)).first
                    if trust_btn.is_visible(timeout=3000):
                        trust_btn.click()
                        page.wait_for_timeout(2000)
                except Exception:
                    pass

            # 4. Wait for Blackboard Ultra landing
            try:
                page.wait_for_url("**/ultra/**", timeout=25000)
            except PlaywrightTimeout:
                pass

            # 5. Extract and save session cookies
            raw_cookies = context.cookies()
            clean_cookies = sanitize_playwright_cookies(raw_cookies)

            with open(LOCAL_COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(clean_cookies, f, indent=2)

            # Verify session via REST API
            valid, user_data = verify_session(clean_cookies)
            browser.close()

            if valid:
                save_stored_credentials(usr, pwd)
                print(f"✅ Authentication successful! Session saved to: {LOCAL_COOKIE_FILE}")
                return True, user_data
            else:
                return False, {"error": "Landed on Blackboard but REST verification failed."}

        except Exception as e:
            try:
                browser.close()
            except Exception:
                pass
            return False, {"error": str(e)}
