import os
import tweepy
import time
import re
from datetime import datetime, timedelta
from typing import List

from dotenv import load_dotenv
from core.models import Episode
from scrapers.base import BaseScraper
from core.utils import pad_text

class TwitterScraper(BaseScraper):
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        load_dotenv()
        self.bearer_token = os.getenv("BEARER_TOKEN")
        
    def scrape(self, target_date: datetime, global_start: float, current_index: int = 1, total_count: int = 1) -> List[Episode]:
        if not self.bearer_token:
            self.logger.error("BEARER_TOKENが設定されていません")
            return []
            
        import time
        user = self.config.get("user")
        programs = self.config.get("programs", [])
        
        tweets = self._search_tweets(target_date, user, programs)
        total_elapsed = time.time() - global_start
        
        eps = self._format_tweets(tweets, programs) if tweets else []
        status = f"{len(eps)}件" if eps else "対象なし"
        progress = f"{current_index}/{total_count}"
        self.logger.info(f"{progress:>5} {pad_text('Twitter(番組情報)', 35)} {pad_text(status, 15)} 経過時間: {int(total_elapsed)}秒")
        
        return eps

    def _search_tweets(self, target_date: datetime, user: str, programs: list, count: int = 20):
        try:
            client = tweepy.Client(bearer_token=self.bearer_token)
            api_query = f"from:{user} ({' OR '.join(programs)})"
            
            # X検索窓用の期間（JST）
            # ツイートは放送日前日にされていることが多い
            search_target = target_date - timedelta(days=1)
            
            # Twitter API v2 の start_time / end_time は UTC
            # Twitter API v2 (Free/Basic) は直近7日間（168時間）しか検索できないためガードを入れる
            now_utc = datetime.utcnow()
            seven_days_ago_utc = now_utc - timedelta(hours=167, minutes=50) # 余裕を持って167時間50分前
            
            # JSTの 00:00:00 〜 23:59:59 は UTCの 前日15:00:00 〜 当日14:59:59
            jst_start = search_target.replace(hour=0, minute=0, second=0)
            jst_end = search_target.replace(hour=23, minute=59, second=59)
            
            start_time_dt = jst_start - timedelta(hours=9)
            end_time_dt = jst_end - timedelta(hours=9)

            if start_time_dt < seven_days_ago_utc:
                if end_time_dt < seven_days_ago_utc:
                    self.logger.warning(f"指定された日付 ({target_date.date()}) はTwitter APIの検索可能範囲（直近7日間）を超えているため、取得をスキップします。")
                    return None
                else:
                    self.logger.warning(f"検索開始時刻が制限を超えているため、取得可能な最古の時刻 ({seven_days_ago_utc.isoformat()}) に調整します。")
                    start_time_dt = seven_days_ago_utc

            start_time = start_time_dt.isoformat() + "Z"
            end_time = end_time_dt.isoformat() + "Z"
            
            self.logger.debug(f"Twitter API Query: {api_query} (Range: {start_time} - {end_time})")
            
            response = client.search_recent_tweets(
                query=api_query,
                max_results=count,
                tweet_fields=["created_at", "text"],
                start_time=start_time,
                end_time=end_time
            )
            
            return response.data
            
        except tweepy.TweepyException as e:
            if isinstance(e, tweepy.errors.TooManyRequests):
                self.logger.warning("Twitter API レート制限超過。待機は行わずスキップします。")
            else:
                self.logger.error(f"Twitter API エラー: {e}")
            return None
        except Exception as e:
            self.logger.error(f"予期せぬエラー: {e}")
            return None

    def _format_tweets(self, tweets: list, programs: list) -> List[Episode]:
        results = []
        for tweet in tweets:
            text = tweet.get("text", "")
            if not text: continue
            
            self.logger.debug(f"ツイートパース中: {text[:50]}...")
            lines = text.splitlines()
            if not lines: continue
            
            first_line = lines[0]
            parts = first_line.split()
            
            channel = ""
            time_info = ""
            if len(parts) >= 3 and parts[0] == "NHK":
                channel = f"NHK {parts[1]}"
                time_match = re.search(r'(午後|午前)\d{1,2}:\d{2}', first_line)
                if time_match:
                    time_info = self._convert_to_24h(time_match.group(0))
                elif re.search(r'\d{1,2}:\d{2}', first_line):
                    # 午前/午後がない場合も考慮
                    raw_time = re.search(r'\d{1,2}:\d{2}', first_line).group(0)
                    time_info = raw_time

            program_name = "抽出失敗"
            for p in programs:
                if p in text:
                    program_name = "Asia Insight" if "Asia" in p else p
                    break
                    
            content = ""
            if len(lines) > 1:
                content = lines[1]
                for p in programs:
                    if p in text:
                        pattern = rf'[ＢＳBS\s]*{re.escape(p)}[🈟▽　選「]*'
                        content = re.sub(pattern, '', content).strip()
                        content = re.sub(r'」$', '', content).strip()
                        break
            
            url = ""
            for line in lines:
                if "https://" in line:
                    url_match = re.search(r'https://t\.co/\w+', line)
                    if url_match:
                        url = url_match.group(0)
                        break
                
            if program_name != "抽出失敗" and content and url:
                self.logger.debug(f"ヒット(Twitter): {program_name} - {content}")
                results.append(Episode(
                    program_name=program_name,
                    channel=channel,
                    title=content,
                    url=url,
                    broadcast_time=time_info
                ))
            else:
                self.logger.debug(f"スキップ(Twitter): program={program_name}, content={bool(content)}, url={bool(url)}")
                
        return results

    def _convert_to_24h(self, time_str: str) -> str:
        m = re.match(r"(午前|午後)(\d{1,2}):(\d{2})", time_str.strip())
        if m:
            ampm, h, m_str = m.group(1), int(m.group(2)), m.group(3)
            if ampm == "午後" and h < 12: h += 12
            elif ampm == "午前" and h == 12: h = 0
            return f"{h:02d}:{m_str}"
        return time_str
