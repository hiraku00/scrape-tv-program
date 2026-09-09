import json
import re
import requests
import traceback
from datetime import datetime
from typing import List

from core.models import Episode
from scrapers.base import BaseScraper

class TVTokyoScraper(BaseScraper):
    def scrape(self, target_date: datetime, global_start: float, current_index: int = 1, total_count: int = 1) -> List[Episode]:
        def fetch_fn(program: dict) -> List[Episode]:
            return self._fetch_program(
                program["name"], program["urls"], program["channel"], program["time"], target_date
            )

        return self._scrape_programs(
            target_date, global_start, current_index, total_count, lambda p: p["name"], fetch_fn
        )

    def _fetch_program(self, name: str, urls: List[str], channel: str, config_time: str, target_date: datetime) -> List[Episode]:
        results = []
        seen_urls = set()
        target_date_norm = target_date.strftime("%Y%m%d")

        for list_url in urls:
            try:
                resp = requests.get(list_url, headers=self.HEADERS, timeout=self.TIMEOUT)
                if resp.status_code != 200: continue
                html = resp.text
                
                # Next.js の JSON を抽出
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', html)
                if not match: continue
                
                data = json.loads(match.group(1))
                page_props = data.get('props', {}).get('pageProps', {})
                server_data = page_props.get('dataFromServer', {})
                
                # 複数のデータパスを試行
                items = (
                    server_data.get('detailResult', {}).get('data') or 
                    server_data.get('items') or 
                    page_props.get('items') or []
                )
                
                if not items:
                    self.logger.debug(f"JSON内にアイテムが見つかりません: {list_url}")
                    continue

                for item in items:
                    raw_date = str(item.get('broadcast_date', ''))
                    clean_date = raw_date.replace('/', '').replace('-', '')
                    title = item.get('episode_name', '').strip()
                    self.logger.debug(f"チェック中: {title} (日付: {raw_date})")

                    if clean_date == target_date_norm:
                        ep_id = item.get('episode_id')
                        # JSON内の放送時間を使用 (例: "22:00:00")。無ければ設定ファイルから。
                        actual_time = item.get('disp_broadcast_time', config_time)
                        if actual_time and len(actual_time) > 5:
                            actual_time = actual_time[:5] # "22:00:00" -> "22:00"
                        
                        # 終了時間の計算
                        final_time_str = actual_time
                        if "-" in config_time and "-" not in actual_time:
                            try:
                                start_conf, end_conf = config_time.split("-")
                                s_dt = datetime.strptime(start_conf, "%H:%M")
                                e_dt = datetime.strptime(end_conf, "%H:%M")
                                duration = e_dt - s_dt
                                actual_s_dt = datetime.strptime(actual_time, "%H:%M")
                                actual_e_dt = actual_s_dt + duration
                                final_time_str = f"{actual_time}-{actual_e_dt.strftime('%H:%M')}"
                            except:
                                final_time_str = f"{actual_time}-"
                        elif "-" in actual_time:
                            final_time_str = actual_time

                        if not ep_id or not title: continue
                        
                        full_url = f"{list_url}/post_{ep_id}"
                        if full_url in seen_urls: continue
                        seen_urls.add(full_url)
                        
                        self.logger.debug(f"ヒット: {title} ({full_url})")
                        results.append(Episode(
                            program_name=name,
                            channel=channel,
                            title=title,
                            url=full_url,
                            broadcast_time=final_time_str
                        ))
            except Exception as e:
                self.logger.error(f"TV東京リクエストエラー ({name} - {list_url}): {e}")
                self.logger.debug(traceback.format_exc())

        return results
