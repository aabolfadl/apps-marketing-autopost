"""Meta's Graph APIs: publishing to Instagram and Facebook Pages, and looking after their tokens."""

import json
import re
import time

import requests

IG_HOST = "https://graph.instagram.com"
FB_HOST = "https://graph.facebook.com"


class MetaError(RuntimeError):
    pass


class Graph:
    def __init__(self, host, version, token):
        self.host = host
        self.version = version
        self.token = token

    def get(self, path, retries=2, **params):
        return self._call("GET", path, params, retries)

    def post(self, path, retries=2, **params):
        """`retries=0` for calls that publish, where a retry after a lost response could post twice."""
        return self._call("POST", path, params, retries)

    def _call(self, method, path, params, retries):
        url = "/".join(part for part in (self.host, self.version, path.lstrip("/")) if part)
        if self.token:
            params = {**params, "access_token": self.token}
        for attempt in range(retries + 1):
            try:
                response = requests.request(
                    method,
                    url,
                    params=params if method == "GET" else None,
                    data=params if method == "POST" else None,
                    timeout=90,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < retries:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise MetaError(f"{method} {path}: {e}") from e
            try:
                body = response.json()
            except ValueError:
                body = {"raw": response.text[:300]}
            error = body.get("error") if isinstance(body, dict) else None
            if response.status_code < 400 and not error:
                return body
            transient = response.status_code >= 500 or (error or {}).get("is_transient")
            if transient and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise MetaError(f"{method} {path}: {describe(body, response.status_code)}")


def describe(body, status):
    error = body.get("error") or {}
    parts = [error.get("message") or body.get("raw") or f"HTTP {status}"]
    for key in ("error_user_title", "error_user_msg"):
        if error.get(key):
            parts.append(error[key])
    codes = ", ".join(f"{k}={error[k]}" for k in ("code", "error_subcode", "fbtrace_id") if error.get(k))
    return " | ".join(parts) + (f" ({codes})" if codes else "")


def _normalise(caption):
    return re.sub(r"\s+", " ", caption or "").strip()[:300]


class Instagram:
    """Instagram API with Instagram Login (graph.instagram.com). Needs a professional account, no Facebook Page."""

    def __init__(self, version, token):
        self.api = Graph(IG_HOST, version, token)

    def me(self):
        return self.api.get("me", fields="user_id,username")

    def publishing_quota(self, user_id):
        """Fails without the instagram_business_content_publish permission, so it doubles as a permission check."""
        data = self.api.get(f"{user_id}/content_publishing_limit", fields="quota_usage,config").get("data", [{}])
        return data[0] if data else {}

    def find_by_caption(self, user_id, caption):
        """A recent post with this caption, if there is one. Guards against posting the same thing twice."""
        wanted = _normalise(caption)
        recent = self.api.get(f"{user_id}/media", fields="id,caption,permalink,timestamp", limit=25)
        return next((m for m in recent.get("data", []) if _normalise(m.get("caption")) == wanted), None)

    def publish(self, user_id, image_urls, caption, say):
        if len(image_urls) == 1:
            container = self._container(user_id, image_url=image_urls[0], caption=caption)
        else:
            children = []
            for i, url in enumerate(image_urls, 1):
                children.append(self._container(user_id, image_url=url, is_carousel_item="true"))
                say(f"  slide {i}/{len(image_urls)} uploaded")
            for child in children:
                self._wait(child)
            container = self._container(user_id, media_type="CAROUSEL", children=",".join(children), caption=caption)
        self._wait(container)
        return self.api.post(f"{user_id}/media_publish", retries=0, creation_id=container)["id"]

    def _container(self, user_id, **fields):
        return self.api.post(f"{user_id}/media", **fields)["id"]

    def _wait(self, container_id, timeout=300):
        deadline = time.monotonic() + timeout
        while True:
            state = self.api.get(container_id, fields="status_code,status")
            code = state.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise MetaError(f"Instagram rejected media container {container_id}: {code} {state.get('status', '')}".strip())
            if time.monotonic() > deadline:
                raise MetaError(f"media container {container_id} still {code} after {timeout}s")
            time.sleep(5)

    def media(self, media_id):
        return self.api.get(media_id, fields="id,permalink,media_type,media_url,timestamp")

    def image_urls(self, media_id):
        """CDN URLs of the images as Instagram now serves them, in slide order."""
        item = self.media(media_id)
        if item.get("media_type") == "CAROUSEL_ALBUM":
            children = self.api.get(f"{media_id}/children", fields="media_type,media_url").get("data", [])
            return [c["media_url"] for c in children if c.get("media_url")]
        return [item["media_url"]] if item.get("media_url") else []


def refresh_instagram_token(token):
    """Swaps a long-lived token (at least 24 hours old) for a new one valid for 60 days."""
    return Graph(IG_HOST, None, token).get("refresh_access_token", grant_type="ig_refresh_token")


class FacebookPage:
    def __init__(self, version, page_id, token):
        self.api = Graph(FB_HOST, version, token)
        self.page_id = page_id

    def name(self):
        return self.api.get(self.page_id, fields="name")["name"]

    def find_by_caption(self, caption):
        wanted = _normalise(caption)
        recent = self.api.get(f"{self.page_id}/posts", fields="id,message,permalink_url", limit=25)
        return next((p for p in recent.get("data", []) if _normalise(p.get("message")) == wanted), None)

    def publish(self, image_urls, caption):
        if len(image_urls) == 1:
            result = self.api.post(f"{self.page_id}/photos", retries=0, url=image_urls[0], caption=caption, published="true")
            return result.get("post_id") or result["id"]
        # Multi-photo post: upload each photo unpublished, then attach them all to one feed post.
        photo_ids = [self.api.post(f"{self.page_id}/photos", url=u, published="false")["id"] for u in image_urls]
        attached = {f"attached_media[{i}]": json.dumps({"media_fbid": pid}) for i, pid in enumerate(photo_ids)}
        return self.api.post(f"{self.page_id}/feed", retries=0, message=caption, **attached)["id"]

    def permalink(self, post_id):
        return self.api.get(post_id, fields="permalink_url").get("permalink_url")


def long_lived_user_token(version, app_id, app_secret, short_token):
    result = Graph(FB_HOST, version, None).get(
        "oauth/access_token",
        grant_type="fb_exchange_token",
        client_id=app_id,
        client_secret=app_secret,
        fb_exchange_token=short_token,
    )
    return result["access_token"]


def managed_pages(version, user_token):
    return Graph(FB_HOST, version, user_token).get("me/accounts", fields="id,name,access_token", limit=100).get("data", [])


def token_info(version, token, app_id, app_secret):
    """What Meta knows about a token: its scopes, expiry and validity."""
    return Graph(FB_HOST, version, f"{app_id}|{app_secret}").get("debug_token", input_token=token)["data"]


def token_expiry(version, token, app_id, app_secret):
    """Unix time the token expires, or 0 for never (what a Page token from a long-lived user token gives)."""
    return token_info(version, token, app_id, app_secret).get("expires_at", 0)
