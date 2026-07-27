"""watch-list APIへ番組情報を登録する処理。"""

from __future__ import annotations

import json
import os
import ssl
from dataclasses import asdict
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import certifi
from dotenv import load_dotenv

from core.models import Episode


class WatchListApiError(RuntimeError):
    """watch-list APIとの通信または応答に関するエラー。"""


def append_episodes_to_watch_list(
    episodes: Iterable[Episode], target_date: str, *, api_url: str | None = None
) -> dict[str, int]:
    """未登録の番組情報をwatch-list DBへ追加し、登録結果を返す。"""
    load_dotenv()
    base_url = _base_api_url(api_url or os.environ.get("WATCH_LIST_API_URL", ""))
    if not base_url:
        raise WatchListApiError("WATCH_LIST_API_URLが設定されていません")

    candidates = _to_api_items(episodes, target_date)
    if not candidates:
        return {"created": 0, "skipped": 0, "errors": 0}

    # Obsidian移行データはURLとは無関係なexternalIdを持つ一方、
    # 番組アーカイブURLは複数放送日で共有されることがあるため、
    # tv-programのexternalIdだけで重複判定する。
    existing_external_ids = _fetch_existing_external_ids(base_url)
    filtered = [
        item for item in candidates
        if (
            item["externalId"] not in existing_external_ids
            and _canonical_url(item["links"][0]["url"]) not in existing_external_ids
        )
    ]
    skipped = len(candidates) - len(filtered)

    created = 0
    errors = 0
    for start in range(0, len(filtered), 200):
        result = _post_import(base_url, filtered[start : start + 200])
        created += int(result.get("created", 0))
        messages = result.get("messages", [])
        errors += int(result.get("errors", 0))
        # 同じexternalIdの再送など、APIがmessagesで返すスキップを件数化する。
        skipped += sum(1 for message in messages if "スキップ" in str(message.get("error", "")))

    return {"created": created, "skipped": skipped, "errors": errors}


def _to_api_items(episodes: Iterable[Episode], target_date: str) -> list[dict]:
    items = []
    seen_urls = set()
    for episode in episodes:
        canonical = _canonical_url(episode.url)
        if not canonical or canonical in seen_urls:
            continue
        seen_urls.add(canonical)
        items.append(
            {
                "contentType": "movie",
                "creatorName": episode.program_name,
                "seriesTitle": "",
                "title": episode.title,
                "description": " ".join(
                    value for value in (episode.channel, episode.broadcast_time) if value
                ),
                "status": "backlog",
                "addedOn": target_date,
                "sourceSystem": "tv-program",
                # 同じアーカイブURLを複数の放送日が共有する場合があるため、
                # 放送日を含めてエピソード単位のIDにする。
                "externalId": f"{target_date}:{canonical}",
                "rawSource": json.dumps(asdict(episode), ensure_ascii=False),
                "links": [{"label": _link_label(episode.url), "url": episode.url, "linkType": "reference"}],
            }
        )
    return items


def _fetch_existing_external_ids(base_url: str) -> set[str]:
    """既存のtv-programデータのexternalIdを取得する。"""
    external_ids = set()
    offset = 0
    while True:
        payload = _request_json(
            f"{base_url}/api/items?limit=100&offset={offset}", method="GET"
        )
        items = payload.get("items", [])
        for item in items:
            if item.get("sourceSystem") == "tv-program" and item.get("externalId"):
                external_ids.add(item["externalId"])
        pagination = payload.get("pagination", {})
        if not pagination.get("hasMore") or not items:
            break
        offset += len(items)
    return external_ids


def _post_import(base_url: str, items: list[dict]) -> dict:
    return _request_json(
        f"{base_url}/api/imports",
        method="POST",
        payload={"sourceName": "tv-program-scraper", "items": items},
    )


def _request_json(url: str, *, method: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        method=method,
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "user-agent": "scrape-tv-program/1.0",
        },
    )
    client_id = _access_credential("WATCH_LIST_ACCESS_CLIENT_ID", "CF-Access-Client-Id")
    client_secret = _access_credential(
        "WATCH_LIST_ACCESS_CLIENT_SECRET", "CF-Access-Client-Secret"
    )
    if client_id and client_secret:
        request.add_header("CF-Access-Client-Id", client_id)
        request.add_header("CF-Access-Client-Secret", client_secret)

    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        with urlopen(request, timeout=20, context=ssl_context) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise WatchListApiError(f"watch-list APIがHTTP {error.code}を返しました: {detail}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise WatchListApiError(f"watch-list APIへの接続に失敗しました: {error}") from error

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise WatchListApiError("watch-list APIの応答がJSONではありません") from error
    if not isinstance(value, dict):
        raise WatchListApiError("watch-list APIの応答形式が不正です")
    return value


def _access_credential(name: str, header_name: str) -> str:
    """環境変数からAccess認証値を取得する（ヘッダー名付き入力にも対応）。"""
    value = os.environ.get(name, "").strip()
    prefix = f"{header_name}:"
    if value.lower().startswith(prefix.lower()):
        value = value[len(prefix) :].strip()
    return value


def _canonical_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return ""
        query = [
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if not (key.startswith("utm_") or key == "fbclid")
        ]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    except ValueError:
        return ""


def _link_label(value: str) -> str:
    """放送URLから利用者に分かりやすいリンク媒体名を返す。"""
    try:
        host = urlsplit(value).netloc.lower().split(":", 1)[0]
    except ValueError:
        return "放送ページ"
    if host == "www.web.nhk" or host.endswith(".web.nhk"):
        return "NHK ONE"
    if host == "txbiz.tv-tokyo.co.jp" or host.endswith(".txbiz.tv-tokyo.co.jp"):
        return "テレ東BIZ"
    if host == "bs.tbs.co.jp" or host.endswith(".bs.tbs.co.jp"):
        return "BS-TBS"
    if host == "tbs.co.jp" or host.endswith(".tbs.co.jp"):
        return "TBS"
    return "放送ページ"


def _base_api_url(value: str) -> str:
    """APIのホストURLだけを取り出し、クエリや末尾スラッシュを除去する。"""
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
