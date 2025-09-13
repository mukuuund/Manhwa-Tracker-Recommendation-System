import os
import re
import html
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta, timezone
from db import get_connection
import requests
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, Message

# ================== Config ==================
EXTS = {".pdf", ".cbz", ".cbr", ".zip", ".rar", ".epub", ".png", ".jpg", ".jpeg", ".webp"}
FOLDER = r"C:\Users\Mukun\Downloads\Telegram Desktop"

# Prefer IANA tz; if unavailable (Windows), fall back to fixed IST offset
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    LOCAL_TZ = ZoneInfo("Asia/Kolkata")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))

# ============== Regex patterns ==============
LEADING_BRACKET_NUM = re.compile(r"^\s*\[\s*(\d+(?:\.\d+)?)\s*\]\s*(.*)$", re.I)
EXPL_CH             = re.compile(r"(?:\bch(?:apter)?|\bep|\bchap)\s*(\d+(?:\.\d+)?)", re.I)
TRAILING_BARE_NUM   = re.compile(r"(?:^|[ \-–_:._])(\d+(?:\.\d+)?)\s*$", re.I)
TRAILING_TAGS       = re.compile(r"\s*[\(\[]\s*(?:eng|raw|hd|scan|color|clean|repack|v\d+|part\s*\d+)\s*[\)\]]\s*$", re.I)
MULTISPACE          = re.compile(r"\s{2,}")

_EXTS_RE = "(?:" + "|".join(re.escape(ext.lstrip(".")) for ext in sorted(EXTS, key=len, reverse=True)) + ")"
CHANNEL_BETWEEN_ANY = re.compile(rf"@([A-Za-z0-9_ ]+)(?=\.{_EXTS_RE}\b)", re.I)

# ============== Utilities ===================
def canonicalize_title(title: str) -> str:
    t = title.replace("-", " ").replace("–", " ").replace("_", " ")
    t = MULTISPACE.sub(" ", t)
    return t.strip().casefold()

def to_local_iso(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")

def fmt_ch(x: Optional[float]) -> str:
    if x is None or x == 0:
        return "-"
    xf = float(x)
    return str(int(xf)) if xf.is_integer() else f"{xf}"

def clean_description(raw: Optional[str]) -> str:
    """AniList descriptions contain HTML & entities; convert to readable text."""
    if not raw:
        return ""
    s = raw
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</?(i|b|em|strong|spoiler)>", "", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)     # strip remaining tags
    s = html.unescape(s)              # &amp; -> &
    s = MULTISPACE.sub(" ", s.replace("\r", "").strip())
    return s.strip()

def snippet(txt: str, max_len: int = 280) -> str:
    if not txt:
        return ""
    t = txt.replace("\n", " ").strip()
    return t if len(t) <= max_len else (t[:max_len - 1] + "…")

# ============== Parsing =====================
def extract_title_and_chapter(stem: str, filename: Optional[str] = None):
    s = stem.replace("_", " ").replace(".", " ").strip()
    channel = None
    if filename:
        m = CHANNEL_BETWEEN_ANY.search(filename)
        if m:
            channel = m.group(1).strip()
            variants = {channel, channel.replace("_", " ")}
            for ch in variants:
                s = re.sub(rf"\s*@{re.escape(ch)}\s*$", " ", s, flags=re.I)
                s = re.sub(rf"\s*@{re.escape(ch)}\b",  " ", s, flags=re.I)

    s = re.sub(r"\s*@[\w _-]+$", " ", s, flags=re.I)

    chapter = None
    m = LEADING_BRACKET_NUM.match(s)
    if m:
        try: chapter = float(m.group(1))
        except ValueError: chapter = None
        s = m.group(2)

    if chapter is None:
        m = EXPL_CH.search(s)
        if m:
            try: chapter = float(m.group(1))
            except ValueError: chapter = None
            s = EXPL_CH.sub("", s)

    if chapter is None:
        m = TRAILING_BARE_NUM.search(s)
        if m:
            try: chapter = float(m.group(1))
            except ValueError: chapter = None
            s = TRAILING_BARE_NUM.sub("", s)

    s = TRAILING_TAGS.sub("", s)
    s = MULTISPACE.sub(" ", s).strip(" -–_:")
    return s or stem, chapter, channel

# ============== Local scan ==================
def list_titles_with_last_chapter(folder: str, debug: bool = False):
    """
    Returns: {title: [last_local_chapter, channel, latest_file_mtime]}
      - latest_file_mtime is a POSIX timestamp (float) for the file that yielded the max chapter.
    """
    root = Path(folder)
    manhwa = {}
    canon_to_display = {}

    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in EXTS:
            continue

        title, ch, channel = extract_title_and_chapter(p.stem, filename=p.name)
        if not title:
            continue

        canon = canonicalize_title(title)
        display = canon_to_display.get(canon) or title
        canon_to_display[canon] = display

        prev_last, prev_channel, prev_mtime = (manhwa.get(display) or [0.0, None, None])

        if ch is not None:
            if ch > prev_last:
                manhwa[display] = [ch, channel or prev_channel, p.stat().st_mtime]
            elif ch == prev_last:
                current_mtime = p.stat().st_mtime
                if prev_mtime is None or current_mtime > prev_mtime:
                    manhwa[display] = [prev_last, channel or prev_channel, current_mtime]
        else:
            if display not in manhwa:
                manhwa[display] = [prev_last, prev_channel, prev_mtime]

    return manhwa

# ============== Telegram scan ===============
def _message_parts(msg: Message):
    parts, file_name = [], None
    if getattr(msg, "message", None):
        parts.append(msg.message)
    if getattr(msg, "file", None) and getattr(msg.file, "name", None):
        file_name = msg.file.name
        parts.append(file_name)
    return parts, file_name

def _build_msg_link(entity, msg: Message) -> Optional[str]:
    if isinstance(entity, Channel) and getattr(entity, "username", None):
        return f"https://t.me/{entity.username}/{msg.id}"
    if isinstance(entity, (Channel, Chat)):
        return f"https://t.me/c/{entity.id}/{msg.id}"
    return None

async def telegram_latest_all_dialogs(
    api_id: int,
    api_hash: str,
    titles: List[str],
    recent_scan: int = 600
) -> Dict[str, Tuple[float, Optional[str], Optional[str], Optional[datetime]]]:
    """
    Scans ALL dialogs (channels + groups).
    Returns: {title: (latest_chapter, dialog_name, permalink, message_date_utc)}
    """
    canon_targets = {canonicalize_title(t): t for t in titles}
    out = {t: (0.0, None, None, None) for t in titles}

    async with TelegramClient("manhwa_session", api_id, api_hash) as client:
        dialogs = []
        async for d in client.iter_dialogs():
            ent = d.entity
            name = (d.name or "").strip()
            if name.lower() == "telegram":
                continue
            if isinstance(ent, Channel) or isinstance(ent, Chat):
                dialogs.append(d)

        for d in dialogs:
            ent = d.entity
            dname = (d.name or "").strip()
            async for msg in client.iter_messages(d.id, limit=recent_scan):
                parts, fname = _message_parts(msg)
                for part in parts:
                    if fname and part == fname:
                        stem = Path(fname).stem
                        title, chno, _ = extract_title_and_chapter(stem, filename=fname)
                    else:
                        title, chno, _ = extract_title_and_chapter(part, filename=None)
                    if not title or chno is None:
                        continue

                    canon = canonicalize_title(title)
                    target_title = canon_targets.get(canon)
                    if not target_title:
                        continue

                    prev_ch, _, _, _ = out[target_title]
                    if chno > prev_ch:
                        out[target_title] = (chno, dname, _build_msg_link(ent, msg), msg.date)

    return out


# ============== AniList lookups =============
def anilist_data(data: dict):
    """
    data = {title: [last_local_ch, channel, ...], ...}
    Returns a list of dicts with AniList info for each title.
    """
    url = 'https://graphql.anilist.co'
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    query = '''
    query ($search: String) {
      Media(search: $search, type: MANGA) {
        title { romaji english }
        status
        chapters
        genres
        description
      }
    }
    '''

    results = []

    for t, v in sorted(data.items()):
        variables = {"search": t}
        try:
            resp = requests.post(
                url,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=20
            )
            js = resp.json()
            media = (js.get("data") or {}).get("Media")
            if not media:
                continue

            title = media.get("title", {}) or {}
            display = title.get("english") or title.get("romaji") or t

            results.append({
                "search": t,
                "display": display,
                "status": media.get("status"),
                "chapters": media.get("chapters"),
                "genres": media.get("genres") or [],
                "description": media.get("description"),
            })
        except Exception:
            continue

    return results

def get_currently_famous_manhwas(limit: int = 20):
    """
    Fetch 'currently famous' manhwas from AniList:
    type: MANGA, countryOfOrigin: KR, status: RELEASING, sort: TRENDING_DESC
    Includes description (raw and cleaned).
    """
    url = "https://graphql.anilist.co"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    query = """
    query TrendingManhwa($page: Int = 1, $perPage: Int = 20) {
      Page(page: $page, perPage: $perPage) {
        media(
          type: MANGA
          countryOfOrigin: KR
          status: RELEASING
          isAdult: false
          sort: TRENDING_DESC
        ) {
          id
          siteUrl
          title { romaji english native }
          status
          chapters
          genres
          averageScore
          popularity
          favourites
          updatedAt
          coverImage { large }
          description
        }
      }
    }
    """
    variables = {"page": 1, "perPage": int(limit)}

    try:
        resp = requests.post(url, json={"query": query, "variables": variables}, headers=headers, timeout=20)
        js = resp.json()
        media_list = (((js.get("data") or {}).get("Page") or {}).get("media") or [])
        out = []
        for m in media_list:
            title = (m.get("title") or {})
            display = title.get("english") or title.get("romaji") or title.get("native") or ""
            raw_desc = m.get("description") or ""
            out.append({
                "display": display,
                "romaji": title.get("romaji"),
                "english": title.get("english"),
                "siteUrl": m.get("siteUrl"),
                "status": m.get("status"),
                "chapters": m.get("chapters"),
                "genres": m.get("genres") or [],
                "averageScore": m.get("averageScore"),
                "popularity": m.get("popularity"),
                "favourites": m.get("favourites"),
                "updatedAt": m.get("updatedAt"),
                "cover": ((m.get("coverImage") or {}).get("large")),
                "description_raw": raw_desc,
                "description": clean_description(raw_desc),
            })
        return out
    except Exception as e:
        print("AniList trending fetch failed:", e)
        return []

def match_famous_with_local(famous: List[dict], local_titles: List[str]):
    """
    Returns two lists:
      have_it: famous titles you already have locally
      missing: famous titles you don't have locally
    Matching is case-insensitive using canonicalize_title.
    """
    have_it, missing = [], []
    canon_local = {canonicalize_title(t): t for t in local_titles}
    for item in famous:
        disp = item.get("display") or ""
        canon = canonicalize_title(disp)
        if canon in canon_local:
            have_it.append({**item, "local_title": canon_local[canon]})
        else:
            missing.append(item)
    return have_it, missing

# ============== DB: ensure table + insert ===
def ensure_trending_table():
    """
    Creates 'trending_manhwa' if missing.
    Uses 'canonical' as unique key. We set refreshed_on during upsert.
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS trending_manhwa (
      id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
      canonical VARCHAR(255) NOT NULL,
      display   VARCHAR(255) NOT NULL,
      site_url  VARCHAR(512) NULL,

      average_score TINYINT UNSIGNED NULL,
      popularity    INT UNSIGNED NULL,
      favourites    INT UNSIGNED NULL,
      genres        JSON NULL,
      chapters_total INT NULL,
      description   MEDIUMTEXT NULL,

      source VARCHAR(32) NOT NULL DEFAULT 'anilist',
      last_trending_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      refreshed_on DATE NOT NULL,  -- set in UPSERT

      inserted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

      UNIQUE KEY uq_trending_canonical (canonical)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    conn = get_connection()
    if not conn:
        return
    cur = conn.cursor()
    cur.execute(ddl)
    conn.commit()
    cur.close()
    conn.close()

def store_trending_famous(famous: List[dict]):
    """
    Insert AniList 'famous' (trending) manhwas into SQL,
    excluding titles already present in local `series` (by canonical),
    and only updating existing rows once per day.
    Assumes table `trending_manhwa` already exists with a UNIQUE(canonical).
    """
    if not famous:
        return

    conn = get_connection()
    if not conn:
        return
    cur = conn.cursor()

    # Staging table for this batch
    cur.execute("""
        CREATE TEMPORARY TABLE tmp_trending_stage (
          canonical      VARCHAR(255) NOT NULL,
          display        VARCHAR(255) NOT NULL,
          site_url       VARCHAR(512) NULL,
          average_score  TINYINT UNSIGNED NULL,
          popularity     INT UNSIGNED NULL,
          favourites     INT UNSIGNED NULL,
          genres         JSON NULL,
          chapters_total INT NULL,
          description    MEDIUMTEXT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    rows = []
    for item in famous:
        display = (item.get("display") or "").strip()
        if not display:
            continue
        canonical = canonicalize_title(display)
        rows.append((
            canonical,
            display,
            item.get("siteUrl"),
            item.get("averageScore"),
            item.get("popularity"),
            item.get("favourites"),
            json.dumps(item.get("genres") or []),
            item.get("chapters"),
            item.get("description") or item.get("description_raw") or "",
        ))

    if rows:
        cur.executemany("""
            INSERT INTO tmp_trending_stage
              (canonical, display, site_url, average_score, popularity, favourites,
               genres, chapters_total, description)
            VALUES (%s,%s,%s,%s,%s,%s,CAST(%s AS JSON),%s,%s);
        """, rows)

        # Insert only those not present locally; upsert with once-per-day guard
        cur.execute("""
            INSERT INTO trending_manhwa (
              canonical, display, site_url,
              average_score, popularity, favourites,
              genres, chapters_total, description,
              last_trending_at, refreshed_on, source
            )
            SELECT
              t.canonical, t.display, t.site_url,
              t.average_score, t.popularity, t.favourites,
              t.genres, t.chapters_total, t.description,
              NOW(), CURRENT_DATE, 'anilist'
            FROM tmp_trending_stage AS t
            LEFT JOIN series s
              ON s.canonical = t.canonical
            WHERE s.canonical IS NULL
            ON DUPLICATE KEY UPDATE
              updated_at       = IF(trending_manhwa.refreshed_on < CURRENT_DATE, CURRENT_TIMESTAMP, trending_manhwa.updated_at),
              display          = IF(trending_manhwa.refreshed_on < CURRENT_DATE, VALUES(display),          trending_manhwa.display),
              site_url         = IF(trending_manhwa.refreshed_on < CURRENT_DATE, VALUES(site_url),         trending_manhwa.site_url),
              average_score    = IF(trending_manhwa.refreshed_on < CURRENT_DATE, VALUES(average_score),    trending_manhwa.average_score),
              popularity       = IF(trending_manhwa.refreshed_on < CURRENT_DATE, VALUES(popularity),       trending_manhwa.popularity),
              favourites       = IF(trending_manhwa.refreshed_on < CURRENT_DATE, VALUES(favourites),       trending_manhwa.favourites),
              genres           = IF(trending_manhwa.refreshed_on < CURRENT_DATE, VALUES(genres),           trending_manhwa.genres),
              chapters_total   = IF(trending_manhwa.refreshed_on < CURRENT_DATE, VALUES(chapters_total),   trending_manhwa.chapters_total),
              description      = IF(trending_manhwa.refreshed_on < CURRENT_DATE, VALUES(description),      trending_manhwa.description),
              last_trending_at = IF(trending_manhwa.refreshed_on < CURRENT_DATE, NOW(),                    trending_manhwa.last_trending_at),
              refreshed_on     = IF(trending_manhwa.refreshed_on < CURRENT_DATE, CURRENT_DATE,             trending_manhwa.refreshed_on);
        """)

    conn.commit()
    cur.close()
    conn.close()

# ======== NEW: persist scan results into `series` ========
def upsert_series(local: Dict[str, list], tg: Dict[str, tuple]) -> None:
    """
    Writes latest local and telegram chapter info into `series`.
    Preserves your schema; uses title + canonical and updates maxima.
    """
    if not local:
        return
    conn = get_connection()
    if not conn:
        return
    cur = conn.cursor()

    rows = []
    for title, (last_local, local_channel, local_mtime) in local.items():
        tg_ch, tg_src, tg_link, tg_dt = tg.get(title, (0.0, None, None, None))
        rows.append((
            title.strip(),
            canonicalize_title(title),
            float(last_local or 0.0),
            local_channel,
            float(tg_ch or 0.0),
            tg_src,
            tg_link,
            (tg_dt.replace(tzinfo=None) if isinstance(tg_dt, datetime) else None)
        ))

    cur.executemany("""
        INSERT INTO series
            (title, canonical,
             local_latest_chapter, channel,
             telegram_latest_chapter, telegram_source, telegram_link, telegram_seen_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            local_latest_chapter    = GREATEST(COALESCE(VALUES(local_latest_chapter),0), COALESCE(series.local_latest_chapter,0)),
            telegram_latest_chapter = GREATEST(COALESCE(VALUES(telegram_latest_chapter),0), COALESCE(series.telegram_latest_chapter,0)),
            channel                 = COALESCE(VALUES(channel), series.channel),
            telegram_source         = COALESCE(VALUES(telegram_source), series.telegram_source),
            telegram_link           = COALESCE(VALUES(telegram_link), series.telegram_link),
            telegram_seen_at        = IFNULL(GREATEST(COALESCE(VALUES(telegram_seen_at), series.telegram_seen_at), series.telegram_seen_at), COALESCE(VALUES(telegram_seen_at), series.telegram_seen_at)),
            updated_at              = CURRENT_TIMESTAMP;
    """, rows)

    conn.commit()
    cur.close()
    conn.close()

# ======== NEW: persist AniList metadata into `manhwa_meta` ========
def upsert_manhwa_meta(meta_rows: List[dict]) -> None:
    """
    Updates or inserts rows in `manhwa_meta` WITHOUT requiring a UNIQUE key.
    Uses search_title as the natural key via UPDATE-then-INSERT per row.
    """
    if not meta_rows:
        return
    conn = get_connection()
    if not conn:
        return
    cur = conn.cursor()

    for m in meta_rows:
        search_title = (m.get("search") or m.get("display") or "").strip()
        if not search_title:
            continue
        display = (m.get("display") or "")[:255]
        status = (m.get("status") or "")[:64]
        chapters_total = m.get("chapters")
        genres_json = json.dumps(m.get("genres") or [])
        description = m.get("description") or ""

        # Try UPDATE first
        cur.execute("""
            UPDATE manhwa_meta
               SET display = %s,
                   status = %s,
                   chapters_total = %s,
                   genres = CAST(%s AS JSON),
                   description = %s,
                   updated_at = CURRENT_TIMESTAMP
             WHERE search_title = %s
        """, (display, status, chapters_total, genres_json, description, search_title))

        if cur.rowcount == 0:
            # No existing row → INSERT
            cur.execute("""
                INSERT INTO manhwa_meta
                    (search_title, display, status, chapters_total, genres, description, updated_at)
                VALUES (%s,%s,%s,%s,CAST(%s AS JSON),%s, CURRENT_TIMESTAMP)
            """, (search_title, display, status, chapters_total, genres_json, description))

    conn.commit()
    cur.close()
    conn.close()

# ================== Main ====================
if __name__ == "__main__":
    load_dotenv()
    API_ID = int(os.getenv("TG_API_ID", "0"))
    API_HASH = os.getenv("TG_API_HASH", "")
    if not API_ID or not API_HASH:
        raise SystemExit("Set TG_API_ID and TG_API_HASH in .env")

    # Local scan
    local = list_titles_with_last_chapter(FOLDER, debug=False)  # {title: [last_local, channel, latest_file_mtime]}
    titles = list(local.keys())

    # Telegram scan
    tg = asyncio.run(telegram_latest_all_dialogs(API_ID, API_HASH, titles, recent_scan=600))

    # ===== NEW: persist latest scan results =====
    upsert_series(local, tg)

    # Optional: fetch AniList info for your local titles and persist to manhwa_meta
    meta_rows = anilist_data(local)
    upsert_manhwa_meta(meta_rows)

    # Build rows for console view (unchanged)
    rows = []
    for t in sorted(titles, key=str.casefold):
        last_local, src_local, local_mtime = (local.get(t) or [0.0, None, None])
        last_tg, src_tg, link, tg_date = tg.get(t, (0.0, None, None, None))
        status = "UP-TO-DATE" if (last_tg <= (last_local or 0.0)) else "NEW!"

        local_dt = None
        if local_mtime is not None:
            local_dt = datetime.fromtimestamp(local_mtime, tz=LOCAL_TZ)
        tg_dt = tg_date.astimezone(LOCAL_TZ) if tg_date else None

        rows.append((
            t,
            fmt_ch(last_local),
            fmt_ch(last_tg),
            src_tg or "-",
            link or "-",
            status,
            to_local_iso(local_dt),
            to_local_iso(tg_dt),
        ))

    # Fetch currently famous (trending) manhwas from AniList
    famous = get_currently_famous_manhwas(limit=20)

    # Compare with local
    have_it, missing = match_famous_with_local(famous, titles)

    # Print (unchanged)
    print("\n=== Currently Famous Manhwas (AniList • TRENDING) ===")
    for i, f in enumerate(famous, 1):
        print(f"{i:>2}. {f['display']}  | score={f['averageScore']}  favs={f['favourites']}  pop={f['popularity']}  -> {f['siteUrl']}")
        if f.get("description"):
            print("    └─", snippet(f["description"]))

    print("\n=== You ALREADY HAVE these famous titles locally ===")
    if not have_it:
        print("(none)")
    else:
        for f in have_it:
            print(f"- {f['local_title']}  (AniList: {f['display']})")

    print("\n=== You DON'T HAVE these famous titles (consider adding) ===")
    if not missing:
        print("(none)")
    else:
        for f in missing:
            print(f"- {f['display']}")

    # ----- Store trending (not present locally), only once per day -----
    ensure_trending_table()
    store_trending_famous(famous)
    print("\nStored trending manhwas to SQL (excluding locals) with daily refresh guard.")
