import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List

from core.models import Episode
from core.utils import pad_text
from scrapers.base import BaseScraper


class BSTBSScraper(BaseScraper):
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    TIMEOUT = 10

    def __init__(self, config: list):
        super().__init__()
        self.config = config

    def scrape(self, target_date: datetime, global_start: float, current_index: int = 1, total_count: int = 1) -> List[Episode]:
        all_episodes = []
        import time

        for idx, program in enumerate(self.config):
            name = program["name"]
            url = program["url"]
            channel = program["channel"]
            time_info = program.get("time", "")

            eps = self._fetch_program(name, url, channel, time_info, target_date)
            total_elapsed = time.time() - global_start

            status = f"{len(eps)}件" if eps else "対象なし"
            i = current_index + idx
            progress = f"{i}/{total_count}"
            self.logger.info(f"{progress:>5} {pad_text(name, 35)} {pad_text(status, 15)} 経過時間: {int(total_elapsed)}秒")

            if eps:
                all_episodes.extend(eps)

        return all_episodes

    def _fetch_program(self, name: str, url: str, channel: str, time_info: str, target_date: datetime) -> List[Episode]:
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=self.TIMEOUT)
            resp.raise_for_status()
            resp.encoding = "utf-8"
        except Exception as e:
            self.logger.error(f"BS-TBSリクエストエラー ({name}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        target_day = target_date.date()

        for archive_block in soup.select("div.shitenmatomeArea"):
            date_tag = archive_block.select_one("p.date")
            if not date_tag:
                continue

            entry_date = self._parse_entry_date(date_tag, target_date.year)
            if not entry_date:
                continue

            if entry_date.date() == target_day:
                title_tag = archive_block.select_one(".descriptionArea h2")
                title = title_tag.get_text("", strip=True) if title_tag else ""
                title = re.sub(r"\s+", "", title)
                if not title:
                    title = "(タイトル未取得)"

                return [Episode(
                    program_name=name,
                    channel=channel,
                    title=title,
                    url=url,
                    broadcast_time=time_info,
                )]

            if entry_date.date() < target_day:
                self.logger.debug(f"{name}: {target_date.strftime('%Y/%m/%d')} は掲載なし。{entry_date.strftime('%Y/%m/%d')} まで確認して停止")
                break

        return []

    def _parse_entry_date(self, date_tag, year: int) -> datetime | None:
        spans = [span.get_text(strip=True) for span in date_tag.find_all("span")]
        if len(spans) >= 2:
            try:
                return datetime(year, int(spans[0]), int(spans[1]))
            except ValueError:
                return None

        text = date_tag.get_text("", strip=True)
        match = re.search(r"(\d{1,2})月(\d{1,2})日", text)
        if not match:
            return None

        try:
            return datetime(year, int(match.group(1)), int(match.group(2)))
        except ValueError:
            return None
