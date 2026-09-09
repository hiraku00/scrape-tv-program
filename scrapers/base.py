import time
from abc import ABC, abstractmethod
from typing import Callable, List
from datetime import datetime
from core.models import Episode
from core.logger import setup_logger
from core.utils import pad_text

class BaseScraper(ABC):
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    TIMEOUT = 10

    def __init__(self, config: list = None):
        self.logger = setup_logger(self.__class__.__name__)
        self.config = config

    @abstractmethod
    def scrape(self, target_date: datetime, global_start: float, current_index: int = 1, total_count: int = 1) -> List[Episode]:
        """
        対象日付の番組情報を取得して Episode オブジェクトのリストを返す
        global_start: 全体の開始時刻(time.time())
        current_index: 現在の処理番号
        total_count: 全体の番組数
        """
        pass

    def _scrape_programs(
        self,
        target_date: datetime,
        global_start: float,
        current_index: int,
        total_count: int,
        name_fn: Callable[[dict], str],
        fetch_fn: Callable[[dict], List[Episode]],
    ) -> List[Episode]:
        """self.config の各番組を fetch_fn で取得し、進捗ログを出しながら結果をまとめる"""
        all_episodes = []
        for idx, program in enumerate(self.config):
            name = name_fn(program)
            eps = fetch_fn(program)
            total_elapsed = time.time() - global_start

            status = f"{len(eps)}件" if eps else "対象なし"
            progress = f"{current_index + idx}/{total_count}"
            self.logger.info(f"{progress:>5} {pad_text(name, 35)} {pad_text(status, 15)} 経過時間: {int(total_elapsed)}秒")

            if eps:
                all_episodes.extend(eps)

        return all_episodes
