import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List

from core.models import Episode
from scrapers.base import BaseScraper
from core.utils import pad_text

class NHKScraper(BaseScraper):
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
            name = program["name"].replace("{year}", str(target_date.year))
            url = program["url"]
            channel = program["channel"]
            
            eps = self._fetch_program(name, url, channel, target_date)
            total_elapsed = time.time() - global_start
            
            status = f"{len(eps)}件" if eps else "対象なし"
            i = current_index + idx
            progress = f"{i}/{total_count}"
            self.logger.info(f"{progress:>5} {pad_text(name, 35)} {pad_text(status, 15)} 経過時間: {int(total_elapsed)}秒")
            
            if eps:
                all_episodes.extend(eps)
            
        return all_episodes

    def _convert_to_24h_format(self, time_str: str) -> str:
        # (変更なし)
        m = re.match(r"(午前|午後)(\d{1,2}):(\d{2})", time_str.strip())
        if m:
            ampm, h, m_str = m.group(1), int(m.group(2)), m.group(3)
            if ampm == "午後" and h < 12:
                h += 12
            elif ampm == "午前" and h == 12:
                h = 0
            return f"{h:02d}:{m_str}"
        return time_str

    def _extract_title_from_anchor(self, a_tag, name: str) -> str:
        p_texts = [p.get_text(" ", strip=True) for p in a_tag.find_all("p")]

        # まず明確なタイトルっぽいテキストを取得
        for text in p_texts:
            if not text or text == name:
                continue
            if re.fullmatch(r"(?:\d{4}年)?\d{1,2}月\d{1,2}日(?:.*)?", text):
                continue
            if re.fullmatch(r"^『.*』の番組エピソードです$", text):
                continue
            if name in text and len(text) > len(name) + 2:
                return text.replace(name, "").strip()
            return text

        # 日付だけしかなければ日付をタイトル扱い
        for text in p_texts:
            if re.fullmatch(r"(?:\d{4}年)?\d{1,2}月\d{1,2}日", text):
                return text

        return ""

    def _is_generic_detail_description(self, text: str) -> bool:
        if not text:
            return True
        text = text.strip()
        if re.fullmatch(r"^【NHK】.*番組エピソードです$", text):
            return True
        if re.fullmatch(r"^.*番組エピソードです$", text):
            return True
        return False

    def _extract_title_from_detail(self, dsoup, name: str) -> str:
        # 優先順序: og:description -> description -> og:title -> title -> h1
        title_text = ""
        for selector in [
            "meta[property='og:description']",
            "meta[name='description']",
        ]:
            tag = dsoup.select_one(selector)
            if tag:
                content = tag.get("content", "").strip()
                if content and not self._is_generic_detail_description(content):
                    title_text = content
                    break

        if not title_text:
            for selector in [
                "meta[property='og:title']",
                "meta[name='title']",
            ]:
                tag = dsoup.select_one(selector)
                if tag:
                    title_text = tag.get("content", "").strip()
                    if title_text:
                        break

        if not title_text:
            title_tag = dsoup.select_one("title")
            if title_tag:
                title_text = title_tag.get_text(" ", strip=True)

        if not title_text:
            heading = dsoup.select_one("h1")
            if heading:
                title_text = heading.get_text(" ", strip=True)

        if title_text:
            title_text = title_text.replace(name, "").strip()
            title_text = re.sub(r"^\s*[-–—|｜]\s*", "", title_text)
            title_text = re.sub(r"\s*[-–—|｜]\s*$", "", title_text)
            title_text = re.sub(r"\s*[-–—|｜]\s*NHK.*$", "", title_text)
            title_text = title_text.strip("「」『』 ")

        return title_text

    def _extract_time_from_detail(self, dsoup, current_time_info: str) -> str:
        time_span = dsoup.select_one("div.f1vveb2x span.f1yrc8pc") or dsoup.select_one("p.f1yrc8pc")
        if time_span:
            time_text = time_span.get_text(strip=True)
            if "-" in time_text:
                parts = time_text.split("-")
                s = self._convert_to_24h_format(parts[0])
                e = self._convert_to_24h_format(parts[1])
                return f"{s}-{e}"
            return self._convert_to_24h_format(time_text)
        return current_time_info

    def _fetch_program(self, name: str, url: str, channel: str, target_date: datetime) -> List[Episode]:
        # (中略) 一覧ページからの取得
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=self.TIMEOUT)
            resp.raise_for_status()
        except Exception as e:
            self.logger.error(f"NHKリクエストエラー ({name}): {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        seen_urls = set()

        for a_tag in soup.find_all("a", href=True):
            text = a_tag.get_text(" ", strip=True)
            href = a_tag["href"]
            if "/ep/" not in href or href in seen_urls:
                continue

            # 日付の抽出 (YYYY年M月D日 または M月D日)
            m_date = re.search(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", text)
            if not m_date: continue
            
            y = int(m_date.group(1)) if m_date.group(1) else target_date.year
            m, d = int(m_date.group(2)), int(m_date.group(3))
            if datetime(y, m, d).date() != target_date.date(): continue

            # タイトル抽出
            title_candidate = self._extract_title_from_anchor(a_tag, name)
            if not title_candidate:
                title_candidate = text
                if "初回放送日" in text:
                    title_candidate = text.split("初回放送日")[0]
                
                # ノイズ除去
                title_candidate = re.sub(r"(?:\d{4}年)?\d{1,2}月\d{1,2}日.*$", "", title_candidate)
                title_candidate = re.sub(r"^\s*(?:\d+時間\s*)?(?:\d+分\s*)?(?:\d+秒\s*)?", "", title_candidate)
                title_candidate = title_candidate.replace(name, "").strip()
                title_candidate = title_candidate.strip("「」『』")

            # 時間情報の抽出
            time_info = ""
            start_time_dt = None
            # 午後11:25 または 23:25
            time_match = re.search(r'((?:午後|午前)?\d{1,2}:\d{2})', text)
            if time_match:
                time_str = time_match.group(1)
                start_time_str = self._convert_to_24h_format(time_str)
                try:
                    start_time_dt = datetime.strptime(start_time_str, "%H:%M")
                    time_info = start_time_str
                except ValueError:
                    pass

            # 放送枠の補正（純粋に記載された放送時間を足す）
            duration_min = 0
            h_match = re.search(r'(\d+)時間', text)
            if h_match:
                duration_min += int(h_match.group(1)) * 60
            m_match = re.search(r'(\d+)分', text)
            if m_match:
                duration_min += int(m_match.group(1))

            if start_time_dt and duration_min > 0:
                from datetime import timedelta
                end_time_dt = start_time_dt + timedelta(minutes=duration_min)
                time_info = f"{start_time_dt.strftime('%H:%M')}-{end_time_dt.strftime('%H:%M')}"

            full_url = href if href.startswith("http") else "https://www.web.nhk" + href
            seen_urls.add(href)

            # 一覧でタイトルが取得できない、あるいは時間情報が不十分な場合、詳細ページへアクセス
            detail_soup = None
            if not title_candidate.strip() or not time_info or "-" not in time_info:
                try:
                    detail_resp = requests.get(full_url, headers=self.HEADERS, timeout=self.TIMEOUT)
                    detail_resp.raise_for_status()
                    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                except Exception as detail_e:
                    if not title_candidate.strip():
                        self.logger.warning(f"NHK詳細ページ取得失敗 ({name}): {detail_e}")
                else:
                    if not title_candidate.strip():
                        title_candidate = self._extract_title_from_detail(detail_soup, name)
                        if not title_candidate.strip():
                            self.logger.warning(f"NHKタイトル抽出失敗 ({name}): {full_url}")
                    if not time_info or "-" not in time_info:
                        time_info = self._extract_time_from_detail(detail_soup, time_info)

            if not title_candidate.strip():
                title_candidate = "(タイトル未取得)"

            results.append(Episode(
                program_name=name,
                channel=channel,
                title=title_candidate,
                url=full_url,
                broadcast_time=time_info
            ))

        return results
