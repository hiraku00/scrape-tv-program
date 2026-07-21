"""Obsidian のウォッチリストへ番組情報を追加するための処理。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from core.models import Episode


DEFAULT_WATCH_LIST_PATH = Path(
    "/Users/hiraku/Obsidian/hiraku-local/04_watch-list/"
    "watch list (text, audio, movie).md"
)


def append_episodes_to_watch_list(
    episodes: Iterable[Episode], target_date: datetime, watch_list_path: Path = DEFAULT_WATCH_LIST_PATH
) -> int:
    """未登録のエピソードをObsidianのMarkdownテーブルへ追加して、追加件数を返す。"""
    if not watch_list_path.exists():
        raise FileNotFoundError(f"ウォッチリストが見つかりません: {watch_list_path}")

    content = watch_list_path.read_text(encoding="utf-8")
    date = f"{target_date.month}/{target_date.day}"
    new_episodes = []
    known_urls = set()

    for episode in episodes:
        if not episode.url or episode.url in known_urls or episode.url in content:
            continue
        known_urls.add(episode.url)
        new_episodes.append(episode)

    if not new_episodes:
        return 0

    rows = [
        _format_watch_list_row(group, date)
        for group in _group_episodes_by_program(new_episodes)
    ]

    lines = content.splitlines(keepends=True)
    insert_at = _watch_list_table_insert_at(lines)
    lines[insert_at:insert_at] = [f"{row}\n" for row in rows]
    watch_list_path.write_text("".join(lines), encoding="utf-8")
    return len(rows)


def _group_episodes_by_program(episodes: Iterable[Episode]) -> list[list[Episode]]:
    grouped = {}
    for episode in episodes:
        key = (_broadcaster_name(episode), episode.program_name)
        grouped.setdefault(key, []).append(episode)
    return list(grouped.values())


def _format_watch_list_row(episodes: list[Episode], date: str) -> str:
    """表の各列に対応する1行を生成する。"""
    first_episode = episodes[0]
    values = [
        _broadcaster_name(first_episode),                 # person
        date,                                             # create date
        "movie",                                         # type
        "<br><br>".join([first_episode.program_name, *[episode.title for episode in episodes]]),
        "",                   # contents
        "",                   # pri
        "",                   # watch date
        "",                   # status
        "<br>".join(episode.url for episode in episodes), # URL
        "",                   # comment
        "",
    ]
    return "| " + " | ".join(_escape_table_cell(value) for value in values) + " |"


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def _broadcaster_name(episode: Episode) -> str:
    """ウォッチリストのperson列用に放送局名を統一する。"""
    if episode.program_name == "報道1930":
        return "TBS"
    if "テレ東" in episode.channel:
        return "テレ東"
    return "NHK"


def _watch_list_table_insert_at(lines: list[str]) -> int:
    """person列を持つ表の末尾（空行を含む）を見つけ、追加位置を返す。"""
    header_index = next(
        (index for index, line in enumerate(lines) if line.startswith("| person")),
        None,
    )
    if header_index is None:
        raise ValueError("ウォッチリストのMarkdownテーブルが見つかりません")

    index = header_index + 2  # 見出し行と配置指定行を飛ばす
    first_empty_row = None
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        if first_empty_row is None and _is_empty_table_row(lines[index]):
            first_empty_row = index
        index += 1

    # 表直後の空行は保持し、その手前にレコードを追加する。
    return first_empty_row if first_empty_row is not None else index


def _is_empty_table_row(line: str) -> bool:
    cells = line.strip().strip("|").split("|")
    return len(cells) >= 10 and not any(cell.strip() for cell in cells)
