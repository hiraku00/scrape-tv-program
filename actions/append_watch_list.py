import re
from datetime import datetime
from pathlib import Path

from core.logger import setup_logger
from core.models import Episode
from core.obsidian import append_episodes_to_watch_list


def run_append_watch_list(target_date_str: str):
    """収集済みの番組情報をObsidianのウォッチリストへ追加する。"""
    logger = setup_logger("append_watch_list")
    target_date = datetime.strptime(target_date_str, "%Y%m%d")
    output_dir = Path(__file__).parent.parent / "output"
    raw_file = output_dir / f"{target_date_str}.raw.txt"
    output_file = raw_file if raw_file.exists() else output_dir / f"{target_date_str}.txt"

    if not output_file.exists():
        logger.error(f"追記対象の収集結果が見つかりません: {output_file}")
        return

    episodes = _parse_output(output_file.read_text(encoding="utf-8"))
    if not episodes:
        logger.warning("追記できる番組情報が見つかりませんでした。")
        return

    try:
        appended_count = append_episodes_to_watch_list(episodes, target_date)
    except (OSError, ValueError) as e:
        logger.error(f"Obsidianのウォッチリストへの追記に失敗しました: {e}")
        return

    logger.info(f"Obsidianのウォッチリストへ{appended_count}行を追加しました")


def _parse_output(content: str) -> list[Episode]:
    """gatherが生成したテキストをEpisodeのリストへ戻す。"""
    episodes = []
    current_program = None
    current_channel = ""
    current_time = ""
    pending_title = None

    for line in content.splitlines():
        if line.startswith("●"):
            current_program, current_channel, current_time = _parse_program_header(line)
            pending_title = None
        elif line.startswith("・"):
            pending_title = line[1:].strip()
        elif pending_title and line.startswith(("http://", "https://")):
            episodes.append(Episode(
                program_name=current_program,
                channel=current_channel,
                title=pending_title,
                url=line.strip(),
                broadcast_time=current_time,
            ))
            pending_title = None

    return episodes


def _parse_program_header(header: str) -> tuple[str, str, str]:
    program_name, details = header[1:].rsplit("(", 1)
    details = details.rstrip(")")
    time_match = re.search(r"\s(\d{1,2}:\d{2}(?:-\d{1,2}:\d{2})?)$", details)
    if time_match:
        return program_name, details[:time_match.start()].strip(), time_match.group(1)
    return program_name, details, ""
