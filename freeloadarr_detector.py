#!/usr/bin/env python3
"""
Plex password-sharing detector using Tautulli.

This version supports DB-backed settings so the web UI can update:
- TAUTULLI_URL
- TAUTULLI_API_KEY
- PUSHBULLET_ACCESS_TOKEN
- LOOKBACK_DAYS
- LIKELY_THRESHOLD
- WATCH_THRESHOLD
- NOTIFY_ON_LIKELY
- NOTIFY_ON_SCORE_INCREASE
- NOTIFY_ON_FIRST_ALERT

Environment variables still work and remain the fallback/default source.
DB-backed settings override environment variables when present.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import logging
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


# -----------------------------
# Helpers
# -----------------------------


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def ts_now() -> int:
    return int(time.time())


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except Exception:
        return default


def is_private_ip(ip: Optional[str]) -> bool:
    if not ip:
        return False
    try:
        obj = ipaddress.ip_address(ip)
        return obj.is_private or obj.is_loopback or obj.is_link_local
    except ValueError:
        return False


def normalize_username(value: Any) -> str:
    return str(value or "").strip()


def safe_json(data: Any) -> str:
    try:
        return json.dumps(data, sort_keys=True, ensure_ascii=False)
    except Exception:
        return "{}"


def overlapping(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    a_end = a_end or ts_now()
    b_end = b_end or ts_now()
    return max(a_start, b_start) < min(a_end, b_end)


# -----------------------------
# Configuration
# -----------------------------


@dataclass
class Config:
    tautulli_url: str
    tautulli_api_key: str
    db_path: str = os.getenv("DB_PATH", "./freeloadarr.db")
    poll_seconds: int = int(os.getenv("POLL_SECONDS", "300"))
    history_length: int = int(os.getenv("HISTORY_LENGTH", "100"))
    lookback_days: int = int(os.getenv("LOOKBACK_DAYS", "14"))
    report_hour: int = int(os.getenv("REPORT_HOUR", "8"))
    discord_webhook_url: Optional[str] = os.getenv("DISCORD_WEBHOOK_URL")
    pushbullet_access_token: Optional[str] = os.getenv("PUSHBULLET_ACCESS_TOKEN")
    exempt_users: set[str] = None
    known_home_ips: dict[str, set[str]] = None
    trust_private_ips: bool = env_bool("TRUST_PRIVATE_IPS", True)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    likely_threshold: int = int(os.getenv("LIKELY_THRESHOLD", "70"))
    watch_threshold: int = int(os.getenv("WATCH_THRESHOLD", "40"))
    notify_on_likely: bool = env_bool("NOTIFY_ON_LIKELY", True)
    notify_on_score_increase: bool = env_bool("NOTIFY_ON_SCORE_INCREASE", False)
    notify_on_first_alert: bool = env_bool("NOTIFY_ON_FIRST_ALERT", True)

    @staticmethod
    def load() -> "Config":
        db_path = os.getenv("DB_PATH", "./freeloadarr.db")
        db_settings = read_settings_from_db(db_path)

        tautulli_url = str(db_settings.get("tautulli_url") or os.getenv("TAUTULLI_URL", "")).rstrip("/")
        tautulli_api_key = str(db_settings.get("tautulli_api_key") or os.getenv("TAUTULLI_API_KEY", ""))
        if not tautulli_url or not tautulli_api_key:
            raise RuntimeError("TAUTULLI_URL and TAUTULLI_API_KEY are required. Set them in env vars or the settings page.")

        exempt_users_raw = os.getenv("EXEMPT_USERS", "")
        exempt_users = {
            user.strip().lower()
            for user in exempt_users_raw.split(",")
            if user.strip()
        }

        known_home_ips_raw = os.getenv("KNOWN_HOME_IPS_JSON", "{}")
        try:
            parsed = json.loads(known_home_ips_raw)
            known_home_ips = {
                str(user).lower(): {str(ip).strip() for ip in ips}
                for user, ips in parsed.items()
            }
        except Exception as exc:
            raise RuntimeError(f"Invalid KNOWN_HOME_IPS_JSON: {exc}") from exc

        return Config(
            tautulli_url=tautulli_url,
            tautulli_api_key=tautulli_api_key,
            db_path=db_path,
            poll_seconds=int(db_settings.get("poll_seconds") or os.getenv("POLL_SECONDS", "300")),
            history_length=int(db_settings.get("history_length") or os.getenv("HISTORY_LENGTH", "100")),
            lookback_days=int(db_settings.get("lookback_days") or os.getenv("LOOKBACK_DAYS", "14")),
            report_hour=int(db_settings.get("report_hour") or os.getenv("REPORT_HOUR", "8")),
            discord_webhook_url=db_settings.get("discord_webhook_url") or os.getenv("DISCORD_WEBHOOK_URL"),
            pushbullet_access_token=db_settings.get("pushbullet_access_token") or os.getenv("PUSHBULLET_ACCESS_TOKEN"),
            exempt_users=exempt_users,
            known_home_ips=known_home_ips,
            trust_private_ips=parse_bool(db_settings.get("trust_private_ips"), env_bool("TRUST_PRIVATE_IPS", True)),
            log_level=str(db_settings.get("log_level") or os.getenv("LOG_LEVEL", "INFO")),
            likely_threshold=int(db_settings.get("likely_threshold") or os.getenv("LIKELY_THRESHOLD", "70")),
            watch_threshold=int(db_settings.get("watch_threshold") or os.getenv("WATCH_THRESHOLD", "40")),
            notify_on_likely=parse_bool(db_settings.get("notify_on_likely"), env_bool("NOTIFY_ON_LIKELY", True)),
            notify_on_score_increase=parse_bool(db_settings.get("notify_on_score_increase"), env_bool("NOTIFY_ON_SCORE_INCREASE", False)),
            notify_on_first_alert=parse_bool(db_settings.get("notify_on_first_alert"), env_bool("NOTIFY_ON_FIRST_ALERT", True)),
        )


# -----------------------------
# Database
# -----------------------------


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT,
    user_id TEXT,
    username TEXT,
    title TEXT,
    started_at INTEGER,
    ended_at INTEGER,
    ip_address TEXT,
    is_private_ip INTEGER,
    is_local INTEGER,
    platform TEXT,
    player TEXT,
    product TEXT,
    device TEXT,
    location TEXT,
    bandwidth INTEGER,
    transcode_decision TEXT,
    raw_json TEXT,
    UNIQUE(session_key, started_at)
);

CREATE TABLE IF NOT EXISTS active_session_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at INTEGER NOT NULL,
    session_key TEXT,
    user_id TEXT,
    username TEXT,
    ip_address TEXT,
    is_private_ip INTEGER,
    is_local INTEGER,
    platform TEXT,
    player TEXT,
    product TEXT,
    device TEXT,
    title TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    username TEXT NOT NULL,
    user_id TEXT,
    alert_type TEXT NOT NULL,
    score INTEGER NOT NULL,
    details TEXT NOT NULL,
    fingerprint TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS user_notes (
    username TEXT PRIMARY KEY,
    status TEXT,
    note TEXT,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS user_score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    recorded_at INTEGER NOT NULL,
    window_days INTEGER NOT NULL,
    score INTEGER NOT NULL,
    classification TEXT NOT NULL,
    UNIQUE(username, recorded_at, window_days)
);

CREATE INDEX IF NOT EXISTS idx_sessions_username_started ON sessions(username, started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_username_ip ON sessions(username, ip_address);
CREATE INDEX IF NOT EXISTS idx_alerts_username_created ON alerts(username, created_at);
CREATE INDEX IF NOT EXISTS idx_score_history_username_window_time ON user_score_history(username, window_days, recorded_at);
"""


def read_settings_from_db(path: str) -> dict[str, str]:
    if not path or not os.path.exists(path):
        return {}
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {str(key): value for key, value in rows}
    except Exception:
        return {}
    finally:
        conn.close()


class Database:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert_session(self, row: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO sessions (
                session_key, user_id, username, title, started_at, ended_at,
                ip_address, is_private_ip, is_local, platform, player, product,
                device, location, bandwidth, transcode_decision, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("session_key"),
                row.get("user_id"),
                row.get("username"),
                row.get("title"),
                row.get("started_at"),
                row.get("ended_at"),
                row.get("ip_address"),
                int(bool(row.get("is_private_ip"))),
                int(bool(row.get("is_local"))),
                row.get("platform"),
                row.get("player"),
                row.get("product"),
                row.get("device"),
                row.get("location"),
                row.get("bandwidth"),
                row.get("transcode_decision"),
                row.get("raw_json"),
            ),
        )
        self.conn.commit()

    def add_active_snapshot(self, row: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO active_session_snapshots (
                observed_at, session_key, user_id, username, ip_address,
                is_private_ip, is_local, platform, player, product, device,
                title, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("observed_at"),
                row.get("session_key"),
                row.get("user_id"),
                row.get("username"),
                row.get("ip_address"),
                int(bool(row.get("is_private_ip"))),
                int(bool(row.get("is_local"))),
                row.get("platform"),
                row.get("player"),
                row.get("product"),
                row.get("device"),
                row.get("title"),
                row.get("raw_json"),
            ),
        )
        self.conn.commit()

    def add_alert(
        self,
        username: str,
        user_id: Optional[str],
        alert_type: str,
        score: int,
        details: str,
        fingerprint: str,
    ) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO alerts (
                created_at, username, user_id, alert_type, score, details, fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(time.time()),
                username,
                user_id,
                alert_type,
                score,
                details,
                fingerprint,
            ),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def fetch_sessions_for_user(self, username: str, since_ts: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM sessions
            WHERE username = ? AND started_at >= ?
            ORDER BY started_at DESC
            """,
            (username, since_ts),
        ).fetchall()

    def fetch_usernames(self, since_ts: int) -> List[str]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT username
            FROM sessions
            WHERE started_at >= ? AND username IS NOT NULL AND username != ''
            ORDER BY username COLLATE NOCASE
            """,
            (since_ts,),
        ).fetchall()
        return [row[0] for row in rows]

    def fetch_recent_alerts(self, since_ts: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM alerts WHERE created_at >= ? ORDER BY score DESC, created_at DESC",
            (since_ts,),
        ).fetchall()

    def fetch_user_note(self, username: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM user_notes WHERE username = ?",
            (username,),
        ).fetchone()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def record_score(self, username: str, window_days: int, score: int, classification: str, recorded_at: Optional[int] = None) -> None:
        recorded_at = recorded_at or ts_now()
        bucket = recorded_at - (recorded_at % 3600)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO user_score_history (username, recorded_at, window_days, score, classification)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, bucket, window_days, score, classification),
        )
        self.conn.commit()

    def fetch_last_recorded_score(self, username: str, window_days: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT *
            FROM user_score_history
            WHERE username = ? AND window_days = ?
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (username, window_days),
        ).fetchone()


# -----------------------------
# Score / classification helpers
# -----------------------------


def classify_score(score: int, likely_threshold: int = 70, watch_threshold: int = 40) -> str:
    if score >= likely_threshold:
        return "likely sharing"
    if score >= watch_threshold:
        return "watch"
    return "normal"


# -----------------------------
# Tautulli API client
# -----------------------------


class TautulliClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()

    def _call(self, cmd: str, **params: Any) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v2"
        query = {"apikey": self.api_key, "cmd": cmd, **params}
        r = self.session.get(url, params=query, timeout=self.timeout)
        r.raise_for_status()
        payload = r.json()
        response = payload.get("response", {})
        if response.get("result") != "success":
            raise RuntimeError(f"Tautulli API call failed for {cmd}: {response}")
        return response.get("data")

    def get_activity(self) -> Dict[str, Any]:
        return self._call("get_activity")

    def get_history(self, length: int = 100, start: int = 0) -> Dict[str, Any]:
        return self._call("get_history", length=length, start=start)


# -----------------------------
# Session normalization
# -----------------------------


def normalize_history_item(item: Dict[str, Any]) -> Dict[str, Any]:
    started = to_int(item.get("started") or item.get("started_at") or item.get("date"))
    stopped = to_int(item.get("stopped") or item.get("stopped_at") or 0)
    ip_addr = item.get("ip_address") or item.get("ip") or item.get("address")
    username = normalize_username(item.get("friendly_name") or item.get("user") or item.get("username"))

    title = (
        item.get("full_title")
        or item.get("grandparent_title")
        or item.get("title")
        or "Unknown"
    )

    return {
        "session_key": str(item.get("session_key") or item.get("reference_id") or item.get("id") or ""),
        "user_id": str(item.get("user_id") or ""),
        "username": username,
        "title": title,
        "started_at": started,
        "ended_at": stopped,
        "ip_address": ip_addr,
        "is_private_ip": is_private_ip(ip_addr),
        "is_local": bool(item.get("location") == "lan" or item.get("secure") == 0),
        "platform": item.get("platform") or item.get("platform_name") or "",
        "player": item.get("player") or "",
        "product": item.get("product") or "",
        "device": item.get("device") or item.get("machine_id") or item.get("player") or "",
        "location": item.get("location") or "",
        "bandwidth": to_int(item.get("bandwidth"), 0),
        "transcode_decision": item.get("transcode_decision") or item.get("stream_video_decision") or "",
        "raw_json": safe_json(item),
    }


def normalize_activity_item(item: Dict[str, Any], observed_at: int) -> Dict[str, Any]:
    ip_addr = item.get("ip_address") or item.get("ip") or item.get("address")
    username = normalize_username(item.get("friendly_name") or item.get("user") or item.get("username"))
    title = (
        item.get("full_title")
        or item.get("grandparent_title")
        or item.get("title")
        or "Unknown"
    )
    return {
        "observed_at": observed_at,
        "session_key": str(item.get("session_key") or ""),
        "user_id": str(item.get("user_id") or ""),
        "username": username,
        "ip_address": ip_addr,
        "is_private_ip": is_private_ip(ip_addr),
        "is_local": bool(item.get("location") == "lan"),
        "platform": item.get("platform") or item.get("platform_name") or "",
        "player": item.get("player") or "",
        "product": item.get("product") or "",
        "device": item.get("device") or item.get("machine_id") or item.get("player") or "",
        "title": title,
        "raw_json": safe_json(item),
    }


# -----------------------------
# Notifications
# -----------------------------


class Notifier:
    def __init__(self, cfg: Config, log: logging.Logger):
        self.cfg = cfg
        self.log = log

    def pushbullet(self, title: str, body: str) -> None:
        token = self.cfg.pushbullet_access_token
        if not token:
            return
        response = requests.post(
            "https://api.pushbullet.com/v2/pushes",
            headers={
                "Access-Token": token,
                "Content-Type": "application/json",
            },
            json={
                "type": "note",
                "title": title,
                "body": body,
            },
            timeout=20,
        )
        response.raise_for_status()

    def discord(self, text: str) -> None:
        if not self.cfg.discord_webhook_url:
            return
        chunks = []
        current = []
        current_len = 0
        for line in text.splitlines(True):
            if current_len + len(line) > 1800 and current:
                chunks.append("".join(current))
                current = [line]
                current_len = len(line)
            else:
                current.append(line)
                current_len += len(line)
        if current:
            chunks.append("".join(current))

        for chunk in chunks:
            r = requests.post(
                self.cfg.discord_webhook_url,
                json={"content": f"```\n{chunk}\n```"},
                timeout=30,
            )
            r.raise_for_status()


# -----------------------------
# Detection logic
# -----------------------------


class Detector:
    def __init__(self, cfg: Config, db: Database, client: TautulliClient):
        self.cfg = cfg
        self.db = db
        self.client = client
        self.log = logging.getLogger("detector")
        self.notifier = Notifier(cfg, self.log)

    def poll_once(self) -> None:
        self.log.info("Polling Tautulli activity and history")
        self._ingest_activity()
        self._ingest_history()
        self._detect_live_overlaps()
        self._score_recent_users()

    def _ingest_activity(self) -> None:
        observed_at = ts_now()
        data = self.client.get_activity() or {}
        sessions = data.get("sessions", []) if isinstance(data, dict) else []
        for item in sessions:
            row = normalize_activity_item(item, observed_at)
            if self._skip_user(row["username"]):
                continue
            self.db.add_active_snapshot(row)
        self.log.info("Ingested %d active sessions", len(sessions))

    def _ingest_history(self) -> None:
        data = self.client.get_history(length=self.cfg.history_length, start=0) or {}
        rows = data.get("data", []) if isinstance(data, dict) else []
        inserted = 0
        for item in rows:
            row = normalize_history_item(item)
            if not row["username"] or self._skip_user(row["username"]):
                continue
            before = self.db.conn.total_changes
            self.db.upsert_session(row)
            if self.db.conn.total_changes > before:
                inserted += 1
        self.log.info("Processed %d history rows (%d new)", len(rows), inserted)

    def _skip_user(self, username: str) -> bool:
        return username.strip().lower() in self.cfg.exempt_users

    def _approved_ip(self, username: str, ip_addr: Optional[str]) -> bool:
        if not username or not ip_addr:
            return False
        approved = self.cfg.known_home_ips.get(username.lower(), set())
        return ip_addr in approved

    def _detect_live_overlaps(self) -> None:
        cutoff = ts_now() - max(self.cfg.poll_seconds * 2, 900)
        rows = self.db.conn.execute(
            """
            SELECT * FROM active_session_snapshots
            WHERE observed_at >= ?
            ORDER BY username, observed_at DESC
            """,
            (cutoff,),
        ).fetchall()

        grouped: dict[str, List[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            username = row["username"]
            if username:
                grouped[username].append(row)

        for username, snapshots in grouped.items():
            by_session: dict[str, sqlite3.Row] = {}
            for snap in snapshots:
                if snap["session_key"] not in by_session:
                    by_session[snap["session_key"]] = snap

            current = list(by_session.values())
            if len(current) < 2:
                continue

            ip_set = {
                row["ip_address"]
                for row in current
                if row["ip_address"] and not (self.cfg.trust_private_ips and row["is_private_ip"])
            }
            if len(ip_set) < 2:
                continue

            score = 60
            if any(self._approved_ip(username, ip_) for ip_ in ip_set):
                score -= 15
            details = {
                "reason": "concurrent streams from different public IPs",
                "ips": sorted(ip_set),
                "sessions": [
                    {
                        "title": row["title"],
                        "device": row["device"],
                        "player": row["player"],
                        "platform": row["platform"],
                        "ip": row["ip_address"],
                    }
                    for row in current
                ],
            }
            fingerprint = f"live-overlap:{username}:{'|'.join(sorted(ip_set))}"
            created = self.db.add_alert(
                username=username,
                user_id=current[0]["user_id"],
                alert_type="live_overlap",
                score=score,
                details=json.dumps(details, ensure_ascii=False),
                fingerprint=fingerprint,
            )
            if created:
                self.log.warning("Live overlap alert for %s (%s)", username, ", ".join(sorted(ip_set)))
                self._maybe_notify(username, score, "live_overlap", details)

    def _score_recent_users(self) -> None:
        main_since_ts = ts_now() - (self.cfg.lookback_days * 86400)
        for username in self.db.fetch_usernames(main_since_ts):
            if self._skip_user(username):
                continue

            for window_days in sorted({1, 7, 14, 30, self.cfg.lookback_days}):
                since_ts = ts_now() - (window_days * 86400)
                window_score, window_summary = self.score_user(username, since_ts)
                self.db.record_score(username, window_days, window_score, window_summary["classification"])

            score, summary = self.score_user(username, main_since_ts)
            if score < self.cfg.watch_threshold:
                continue

            fingerprint = (
                f"window-score:{username}:{dt.datetime.utcfromtimestamp(main_since_ts).date()}:"
                f"{score}:{summary['distinct_public_ips']}:{summary['distinct_devices']}:{summary['overlap_events']}"
            )
            created = self.db.add_alert(
                username=username,
                user_id=summary.get("user_id"),
                alert_type="rolling_window_score",
                score=score,
                details=json.dumps(summary, ensure_ascii=False),
                fingerprint=fingerprint,
            )
            if created:
                self._maybe_notify(username, score, "rolling_window_score", summary)

    def _maybe_notify(self, username: str, score: int, alert_type: str, details: dict[str, Any]) -> None:
        classification = classify_score(score, self.cfg.likely_threshold, self.cfg.watch_threshold)
        last_score_row = self.db.fetch_last_recorded_score(username, self.cfg.lookback_days)
        previous_score = int(last_score_row["score"]) if last_score_row else None

        should_notify = False
        reasons = []

        if self.cfg.notify_on_first_alert and previous_score is None:
            should_notify = True
            reasons.append("first alert")
        if self.cfg.notify_on_likely and score >= self.cfg.likely_threshold:
            should_notify = True
            reasons.append("likely threshold")
        if self.cfg.notify_on_score_increase and previous_score is not None and score > previous_score:
            should_notify = True
            reasons.append("score increase")

        if not should_notify:
            return

        body_lines = [
            f"User: {username}",
            f"Alert type: {alert_type}",
            f"Score: {score} ({classification})",
            f"Reason: {', '.join(reasons)}",
        ]
        if isinstance(details, dict):
            if details.get("reason"):
                body_lines.append(f"Signal: {details['reason']}")
            if details.get("reasons"):
                body_lines.extend([f"- {r}" for r in details["reasons"][:5]])
            if details.get("ips"):
                body_lines.append("IPs: " + ", ".join(details["ips"][:6]))
            if details.get("public_ips"):
                body_lines.append("Public IPs: " + ", ".join(details["public_ips"][:6]))

        message = "\n".join(body_lines)
        try:
            self.notifier.pushbullet(f"Freeloadarr: {username}", message)
        except Exception:
            self.log.exception("Failed to send Pushbullet notification")

    def score_user(self, username: str, since_ts: int) -> Tuple[int, Dict[str, Any]]:
        sessions = self.db.fetch_sessions_for_user(username, since_ts)
        if not sessions:
            return 0, {
                "username": username,
                "user_id": None,
                "score": 0,
                "classification": classify_score(
                    0,
                    self.cfg.likely_threshold,
                    self.cfg.watch_threshold,
                ),
                "distinct_public_ips": 0,
                "distinct_devices": 0,
                "distinct_platforms": 0,
                "stable_public_ips": [],
                "overlap_events": 0,
                "session_count": 0,
                "reasons": [],
                "score_breakdown": [],
                "ips": [],
                "devices": [],
                "platforms": [],
            }

        public_ips = []
        devices = set()
        platforms = set()
        overlap_events = []
        stable_ips = Counter()
        user_id = sessions[0]["user_id"]

        normalized = []
        for row in sessions:
            ip_addr = row["ip_address"]
            if ip_addr and not (self.cfg.trust_private_ips and row["is_private_ip"]):
                public_ips.append(ip_addr)
                stable_ips[ip_addr] += 1
            if row["device"]:
                devices.add(row["device"])
            if row["platform"]:
                platforms.add(row["platform"])
            normalized.append(row)

        ordered = sorted(normalized, key=lambda r: r["started_at"])
        for i in range(len(ordered)):
            a = ordered[i]
            for j in range(i + 1, len(ordered)):
                b = ordered[j]
                if b["started_at"] > (a["ended_at"] or ts_now()):
                    break
                if not overlapping(a["started_at"], a["ended_at"], b["started_at"], b["ended_at"]):
                    continue
                a_ip = a["ip_address"]
                b_ip = b["ip_address"]
                if not a_ip or not b_ip or a_ip == b_ip:
                    continue
                if self.cfg.trust_private_ips and (a["is_private_ip"] or b["is_private_ip"]):
                    continue
                overlap_events.append(
                    {
                        "a_title": a["title"],
                        "b_title": b["title"],
                        "a_ip": a_ip,
                        "b_ip": b_ip,
                        "a_start": a["started_at"],
                        "b_start": b["started_at"],
                    }
                )

        distinct_public_ips = sorted(set(public_ips))
        stable_public_ips = [ip for ip, count in stable_ips.items() if count >= 2]

        score = 0
        reasons = []
        score_breakdown = []

        if overlap_events:
            overlap_score = min(60 + (len(overlap_events) - 1) * 10, 90)
            score += overlap_score
            reasons.append(f"{len(overlap_events)} overlapping session event(s) across different public IPs (+{overlap_score})")
            score_breakdown.append({"label": "Overlapping sessions", "points": overlap_score})

        if len(distinct_public_ips) >= 4:
            score += 20
            reasons.append(f"{len(distinct_public_ips)} distinct public IPs in lookback window (+20)")
            score_breakdown.append({"label": "Distinct public IPs", "points": 20})
        elif len(distinct_public_ips) == 3:
            score += 10
            reasons.append("3 distinct public IPs in lookback window (+10)")
            score_breakdown.append({"label": "Distinct public IPs", "points": 10})

        if len(devices) >= 5:
            score += 15
            reasons.append(f"{len(devices)} distinct devices (+15)")
            score_breakdown.append({"label": "Distinct devices", "points": 15})
        elif len(devices) >= 3:
            score += 8
            reasons.append(f"{len(devices)} distinct devices (+8)")
            score_breakdown.append({"label": "Distinct devices", "points": 8})

        if len(platforms) >= 4:
            score += 10
            reasons.append(f"{len(platforms)} distinct platforms (+10)")
            score_breakdown.append({"label": "Distinct platforms", "points": 10})

        if len(stable_public_ips) >= 2:
            score += 25
            reasons.append(f"multiple stable public IPs observed repeatedly ({len(stable_public_ips)}) (+25)")
            score_breakdown.append({"label": "Stable public IPs", "points": 25})

        approved_hits = sum(1 for ip in distinct_public_ips if self._approved_ip(username, ip))
        if approved_hits:
            deduction = min(approved_hits * 10, 20)
            score -= deduction
            reasons.append(f"approved known-home IP match(es): {approved_hits} (-{deduction})")
            score_breakdown.append({"label": "Approved IP deduction", "points": -deduction})

        score = max(score, 0)
        summary = {
            "username": username,
            "user_id": user_id,
            "score": score,
            "classification": classify_score(score, self.cfg.likely_threshold, self.cfg.watch_threshold),
            "reasons": reasons,
            "score_breakdown": score_breakdown,
            "distinct_public_ips": len(distinct_public_ips),
            "public_ips": distinct_public_ips,
            "distinct_devices": len(devices),
            "devices": sorted(devices),
            "distinct_platforms": len(platforms),
            "platforms": sorted(platforms),
            "stable_public_ips": sorted(stable_public_ips),
            "overlap_events": len(overlap_events),
            "sample_overlap_events": overlap_events[:5],
            "session_count": len(sessions),
            "review_note": self._review_note(username),
        }
        return score, summary

    def _review_note(self, username: str) -> Optional[Dict[str, Any]]:
        row = self.db.fetch_user_note(username)
        if not row:
            return None
        return {"status": row["status"], "note": row["note"], "updated_at": row["updated_at"]}

    def build_daily_report(self) -> str:
        since_ts = ts_now() - (self.cfg.lookback_days * 86400)
        user_summaries = []
        for username in self.db.fetch_usernames(since_ts):
            if self._skip_user(username):
                continue
            score, summary = self.score_user(username, since_ts)
            if score <= 0:
                continue
            user_summaries.append(summary)

        user_summaries.sort(key=lambda s: s["score"], reverse=True)
        recent_alerts = self.db.fetch_recent_alerts(ts_now() - 86400)

        lines = []
        lines.append(f"Freeloadarr report — generated {dt.datetime.now().isoformat(timespec='seconds')}")
        lines.append(f"Lookback window: last {self.cfg.lookback_days} day(s)")
        lines.append("")

        if recent_alerts:
            lines.append(f"Alerts in last 24h: {len(recent_alerts)}")
            for row in recent_alerts[:15]:
                created = dt.datetime.fromtimestamp(row["created_at"]).isoformat(sep=' ', timespec='minutes')
                lines.append(f"- [{row['score']:>2}] {row['username']} :: {row['alert_type']} :: {created}")
            lines.append("")
        else:
            lines.append("Alerts in last 24h: 0")
            lines.append("")

        if not user_summaries:
            lines.append("No suspicious activity found.")
            return "\n".join(lines)

        for summary in user_summaries:
            lines.append(f"{summary['username']} — score {summary['score']} ({summary['classification']})")
            for reason in summary["reasons"]:
                lines.append(f"  • {reason}")
            lines.append(f"  • Distinct public IPs: {summary['distinct_public_ips']} -> {', '.join(summary['public_ips']) or 'none'}")
            lines.append(f"  • Devices: {summary['distinct_devices']} -> {', '.join(summary['devices']) or 'none'}")
            lines.append(f"  • Platforms: {summary['distinct_platforms']} -> {', '.join(summary['platforms']) or 'none'}")
            lines.append(f"  • Overlap events: {summary['overlap_events']}")
            if summary["review_note"]:
                lines.append(f"  • Review note: {summary['review_note']['status']} — {summary['review_note']['note']}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def deliver_report(self, report_text: str) -> None:
        delivered = False
        if self.cfg.discord_webhook_url:
            try:
                self.notifier.discord(report_text)
                delivered = True
            except Exception:
                self.log.exception("Failed to send report to Discord")
        if self.cfg.pushbullet_access_token:
            try:
                self.notifier.pushbullet("Freeloadarr Daily Report", report_text[:4000])
                delivered = True
            except Exception:
                self.log.exception("Failed to send report to Pushbullet")
        if not delivered:
            self.log.info("No delivery destination set; printing report instead")
            print(report_text)


# -----------------------------
# Main loop
# -----------------------------


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def seconds_until_hour(hour_24: int) -> int:
    now = dt.datetime.now()
    target = now.replace(hour=hour_24, minute=0, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return int((target - now).total_seconds())


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect likely Plex password sharing using Tautulli data.")
    parser.add_argument("--once", action="store_true", help="Run one poll cycle and exit")
    parser.add_argument("--report-now", action="store_true", help="Generate report immediately and exit")
    args = parser.parse_args()

    try:
        cfg = Config.load()
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    setup_logging(cfg.log_level)
    log = logging.getLogger("main")

    db = Database(cfg.db_path)
    client = TautulliClient(cfg.tautulli_url, cfg.tautulli_api_key)
    detector = Detector(cfg, db, client)

    try:
        if args.report_now:
            report = detector.build_daily_report()
            detector.deliver_report(report)
            return 0

        if args.once:
            detector.poll_once()
            return 0

        next_report_at = time.time() + seconds_until_hour(cfg.report_hour)
        log.info(
            "Starting continuous mode; next report scheduled at %s",
            dt.datetime.fromtimestamp(next_report_at).isoformat(timespec="seconds"),
        )

        while True:
            try:
                detector.poll_once()
            except Exception:
                log.exception("Poll failed")

            if time.time() >= next_report_at:
                try:
                    report = detector.build_daily_report()
                    detector.deliver_report(report)
                except Exception:
                    log.exception("Failed to build or deliver report")
                next_report_at = time.time() + seconds_until_hour(cfg.report_hour)

            time.sleep(cfg.poll_seconds)
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
