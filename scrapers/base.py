from abc import ABC, abstractmethod
from typing import List
from datetime import datetime
from core.models import Episode
from core.logger import setup_logger

class BaseScraper(ABC):
    def __init__(self):
        self.logger = setup_logger(self.__class__.__name__)
        
    @abstractmethod
    def scrape(self, target_date: datetime, global_start: float, current_index: int = 1, total_count: int = 1) -> List[Episode]:
        """
        対象日付の番組情報を取得して Episode オブジェクトのリストを返す
        global_start: 全体の開始時刻(time.time())
        current_index: 現在の処理番号
        total_count: 全体の番組数
        """
        pass
