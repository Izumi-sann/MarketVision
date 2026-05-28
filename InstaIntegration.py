from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import instaloader
import requests
import json
import re


@dataclass
class PostRecord:
    username: str
    shortcode: str
    post_url: str
    post_type: str
    posted_at: datetime
    likes: int
    comments: int
    views: int | None
    caption: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["posted_at"] = self.posted_at.isoformat()
        return payload


def _classify_post(post: Any) -> str:
    if getattr(post, "typename", "") == "GraphSidecar":
        return "carousel"

    if getattr(post, "is_video", False):
        product_type = str(getattr(post, "product_type", "") or "").lower()
        if product_type == "clips":
            return "reel"
        return "video"

    return "photo"


def fetch_public_profile_posts(
    username: str,
    max_posts: int = 12,
    login_username: str | None = None,
    login_password: str | None = None,
) -> list[PostRecord]:
    username = username.strip().lstrip("@")
    if not username:
        raise ValueError("Username Instagram non valido")

    loader = instaloader.Instaloader(
        download_videos=False,
        download_video_thumbnails=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )

    login_username = login_username or os.getenv("IG_LOGIN_USERNAME")
    login_password = login_password or os.getenv("IG_LOGIN_PASSWORD")

    # Prefer loading a saved session to avoid re-login and 2FA prompts.
    if login_username:
        try:
            # Try explicit session file in workspace first ('.session-<username>').
            session_path = os.path.join(os.getcwd(), f".session-{login_username}")
            if os.path.exists(session_path):
                loader.load_session_from_file(login_username, filename=session_path)
            else:
                loader.load_session_from_file(login_username)
        except Exception:
            # No session file or failed to load; try login if password provided
            if login_password:
                try:
                    loader.login(login_username, login_password)
                    try:
                        loader.save_session_to_file(login_username)
                    except Exception:
                        # Non-fatal: session saving failed
                        pass
                except Exception as exc:
                    # Surface a clearer error for wrong credentials or 2FA
                    msg = str(exc)
                    if "bad credentials" in msg.lower() or "wrong" in msg.lower():
                        raise ValueError("Login error: Wrong username or password.")
                    if "two-factor" in msg.lower() or "challenge" in msg.lower():
                        raise ValueError(
                            "Login requires two-factor or challenge flow. Create a session interactively with `instaloader -l USERNAME` and retry."
                        )
                    raise ValueError(f"Login error: {exc}")
            # else: no password provided — continue unauthenticated

    records: list[PostRecord] = []

    # First try with Instaloader (preferred)
    try:
        profile = instaloader.Profile.from_username(loader.context, username)
        for post in profile.get_posts():
            if len(records) >= max_posts:
                break

            records.append(
                PostRecord(
                    username=username,
                    shortcode=post.shortcode,
                    post_url=f"https://www.instagram.com/p/{post.shortcode}/",
                    post_type=_classify_post(post),
                    posted_at=post.date_utc,
                    likes=int(getattr(post, "likes", 0) or 0),
                    comments=int(getattr(post, "comments", 0) or 0),
                    views=(int(getattr(post, "video_view_count", 0) or 0) if getattr(post, "is_video", False) else None),
                    caption=getattr(post, "caption", None),
                )
            )
        if records:
            return records
    except Exception:
        # Fall back to HTML scraping for public profiles
        pass

    # HTML fallback: fetch the profile page and parse shared JSON data
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        resp = requests.get(f"https://www.instagram.com/{username}/", headers=headers, timeout=15)
        resp.raise_for_status()
        text = resp.text

        # Find window._sharedData = {...}; pattern
        m = re.search(r"window\._sharedData\s*=\s*(\{.*?\})\s*;\s*</script>", text, flags=re.DOTALL)
        payload = None
        if m:
            try:
                payload = json.loads(m.group(1))
            except Exception:
                payload = None

        if not payload:
            # Try to find JSON inside <script type="application/ld+json">
            m2 = re.search(r"<script type=\"application/ld\+json\">(\{.*?\})</script>", text, flags=re.DOTALL)
            if m2:
                try:
                    payload = json.loads(m2.group(1))
                except Exception:
                    payload = None

        if payload:
            # Traverse to timeline media edges
            print("DEBUG: payload found in HTML")
            edges = None
            try:
                edges = payload.get("entry_data", {}).get("ProfilePage", [])[0].get("graphql", {}).get("user", {}).get("edge_owner_to_timeline_media", {}).get("edges", [])
            except Exception:
                edges = None

            if not edges:
                # Some pages embed JSON under sharedData->graphql
                try:
                    entries = payload.get("graphql", {})
                    if entries:
                        edges = entries.get("user", {}).get("edge_owner_to_timeline_media", {}).get("edges", [])
                except Exception:
                    edges = None

            if edges:
                for edge in edges[:max_posts]:
                    node = edge.get("node", {})
                    shortcode = node.get("shortcode")
                    is_video = node.get("is_video", False)
                    likes = node.get("edge_liked_by", {}).get("count") or node.get("edge_media_preview_like", {}).get("count") or 0
                    comments = node.get("edge_media_to_comment", {}).get("count") or 0
                    ts = node.get("taken_at_timestamp")
                    views = node.get("video_view_count") if is_video else None
                    posted_at = datetime.utcfromtimestamp(int(ts)) if ts else datetime.utcnow()
                    records.append(
                        PostRecord(
                            username=username,
                            shortcode=shortcode,
                            post_url=f"https://www.instagram.com/p/{shortcode}/" if shortcode else f"https://www.instagram.com/{username}/",
                            post_type=("video" if is_video else "photo"),
                            posted_at=posted_at,
                            likes=int(likes or 0),
                            comments=int(comments or 0),
                            views=int(views) if views is not None else None,
                            caption=node.get("edge_media_to_caption", {}).get("edges", [])[0].get("node", {}).get("text") if node.get("edge_media_to_caption", {}).get("edges") else None,
                        )
                    )

                if records:
                    return records

    except Exception:
        pass

    # API-like fallback: use the web_profile_info endpoint with x-ig-app-id header
    try:
        api_headers = {"User-Agent": "Mozilla/5.0", "x-ig-app-id": "936619743392459"}
        api_resp = requests.get(f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}", headers=api_headers, timeout=15)
        if api_resp.status_code == 200:
            j = api_resp.json()
            user = j.get("data", {}).get("user") or j.get("user")
            if user:
                edges = user.get("edge_owner_to_timeline_media", {}).get("edges", [])
                for edge in edges[:max_posts]:
                    node = edge.get("node", {})
                    shortcode = node.get("shortcode")
                    is_video = node.get("is_video", False)
                    ts = node.get("taken_at_timestamp")
                    posted_at = datetime.utcfromtimestamp(int(ts)) if ts else datetime.utcnow()
                    likes = node.get("edge_liked_by", {}).get("count") or node.get("edge_media_preview_like", {}).get("count") or 0
                    comments = node.get("edge_media_to_comment", {}).get("count") or 0
                    records.append(
                        PostRecord(
                            username=username,
                            shortcode=shortcode,
                            post_url=f"https://www.instagram.com/p/{shortcode}/" if shortcode else f"https://www.instagram.com/{username}/",
                            post_type=("video" if is_video else "photo"),
                            posted_at=posted_at,
                            likes=int(likes or 0),
                            comments=int(comments or 0),
                            views=(int(node.get("video_view_count")) if is_video and node.get("video_view_count") is not None else None),
                            caption=(node.get("edge_media_to_caption", {}).get("edges", [])[0].get("node", {}).get("text") if node.get("edge_media_to_caption", {}).get("edges") else None),
                        )
                    )

                if records:
                    return records
    except Exception:
        pass
    # Playwright fallback: render the page and extract post links + timestamps
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36"),
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.goto(f"https://www.instagram.com/{username}/", wait_until="networkidle", timeout=30000)

            # Wait for the main article grid to appear
            try:
                page.wait_for_selector('article', timeout=15000)
            except Exception:
                # If no article, close and fallback
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass
                raise

            # Extract post hrefs using page.evaluate for reliability
            try:
                hrefs = page.eval_on_selector_all('article a[href^="/p/"]', 'els => els.map(e => e.getAttribute("href"))')
            except Exception:
                hrefs = []

            seen = set()
            for href in (hrefs or [])[: max_posts * 2]:
                if len(records) >= max_posts:
                    break
                if not href or href in seen:
                    continue
                seen.add(href)
                post_url = f"https://www.instagram.com{href}"
                # Open post in a new page to isolate navigation
                try:
                    post_page = context.new_page()
                    post_page.goto(post_url, wait_until="networkidle", timeout=20000)
                    # get ISO datetime from time tag
                    time_el = post_page.query_selector('time')
                    datetime_str = time_el.get_attribute('datetime') if time_el else None
                    is_video = bool(post_page.query_selector('video'))
                    posted_at = datetime.fromisoformat(datetime_str.replace('Z', '+00:00')) if datetime_str else datetime.utcnow()
                    post_page.close()
                except Exception:
                    posted_at = datetime.utcnow()
                    is_video = False
                    try:
                        post_page.close()
                    except Exception:
                        pass

                records.append(
                    PostRecord(
                        username=username,
                        shortcode=href.strip('/').split('/')[-1],
                        post_url=post_url,
                        post_type=("video" if is_video else "photo"),
                        posted_at=posted_at,
                        likes=0,
                        comments=0,
                        views=None,
                        caption=None,
                    )
                )

            try:
                context.close()
                browser.close()
            except Exception:
                pass

            if records:
                return records
    except Exception:
        pass

    raise ValueError(f"Profile {username} does not exist or is not accessible.")


def summarize_posts(posts: list[PostRecord]) -> dict[str, Any]:
    if not posts:
        return {
            "count": 0,
            "avg_days_between_posts": None,
            "last_posted_at": None,
            "avg_likes": None,
            "avg_comments": None,
            "avg_views": None,
            "type_counts": {},
        }

    ordered_posts = sorted(posts, key=lambda item: item.posted_at)
    deltas = [
        (right.posted_at - left.posted_at).total_seconds() / 86400
        for left, right in zip(ordered_posts, ordered_posts[1:])
    ]

    type_counts: dict[str, int] = {}
    total_likes = 0
    total_comments = 0
    total_views = 0
    views_count = 0

    for post in posts:
        type_counts[post.post_type] = type_counts.get(post.post_type, 0) + 1
        total_likes += post.likes
        total_comments += post.comments
        if post.views is not None:
            total_views += post.views
            views_count += 1

    return {
        "count": len(posts),
        "avg_days_between_posts": round(sum(deltas) / len(deltas), 2) if deltas else None,
        "last_posted_at": max(post.posted_at for post in posts),
        "avg_likes": round(total_likes / len(posts), 2),
        "avg_comments": round(total_comments / len(posts), 2),
        "avg_views": round(total_views / views_count, 2) if views_count else None,
        "type_counts": type_counts,
    }


def fetch_official_insights(
    ig_user_id: str,
    access_token: str | None = None,
) -> list[dict[str, Any]]:
    token = access_token or os.getenv("ACCESS_TOKEN")
    if not token:
        raise ValueError("ACCESS_TOKEN mancante")

    user_id = ig_user_id.strip()
    if not user_id:
        raise ValueError("IG_USER_ID mancante")

    url = f"https://graph.facebook.com/v19.0/{user_id}/insights"
    insights: list[dict[str, Any]] = []

    for metric in ("profile_views", "views"):
        params = {
            "metric": metric,
            "metric_type": "total_value",
            "period": "day",
            "access_token": token,
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        insights.extend(payload.get("data", []))

    return insights


if __name__ == "__main__":
    ig_user_id = os.getenv("IG_USER_ID")
    if ig_user_id:
        for metric in fetch_official_insights(ig_user_id):
            name = metric.get("name")
            values = metric.get("values", [])
            value = values[0].get("value") if values else None
            print(f"{name}: {value}")
    