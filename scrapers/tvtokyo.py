import json
import re
import requests
from datetime import datetime
from typing import List

from core.models import Episode
from scrapers.base import BaseScraper
from core.utils import pad_text

class TVTokyoScraper(BaseScraper):
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
            channel = program["channel"]
            time_info = program["time"]
            urls = program["urls"]
            
            eps = self._fetch_program(name, urls, channel, time_info, target_date)
            total_elapsed = time.time() - global_start
            
            status = f"{len(eps)}件" if eps else "対象なし"
            i = current_index + idx
            progress = f"{i}/{total_count}"
            self.logger.info(f"{progress:>5} {pad_text(name, 35)} {pad_text(status, 15)} 経過時間: {int(total_elapsed)}秒")
            
            if eps:
                all_episodes.extend(eps)
            
        return all_episodes

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
                import traceback
                self.logger.debug(traceback.format_exc())

        return results
