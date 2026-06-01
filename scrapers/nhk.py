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

    def _extract_title_from_anchor(self, a_tag, name: str) -> tuple[str, str]:
        p_texts = [p.get_text(" ", strip=True) for p in a_tag.find_all("p")]
        p_texts = [t for t in p_texts if t.strip()]  # 空文字のpタグを除外

        # NOTE: NHKの一覧では番組名の表記ゆれ（例: 半角'!' と全角'！'）があり、
        #       そのまま番組名を削除すると空文字になってしまう場合がある。
        #       対策: 句読点を正規化して比較し、<p>が番組名そのものなら番組名を返す。

        def _normalize_punct(s: str) -> str:
            if not s:
                return s
            # 句読点を全角に正規化してNHKのテキストと一致しやすくする
            return s.replace("!", "！").replace("?", "？").replace(":", "：").strip()

        # 要素数が3つ以上の場合、通常は
        # p[0]: 番組タイトル（サブタイトルやキャッチコピー等を含む）
        # p[1]: 各回固有のエピソードタイトル
        # p[2]: あらすじ・説明文
        # となっているため、p[0]を番組名、p[1]をエピソードタイトルとして採用する。
        if len(p_texts) >= 3:
            prog_name_candidate = p_texts[0]
            title_candidate = p_texts[1]
            if (not re.fullmatch(r"(?:\d{4}年)?\d{1,2}月\d{1,2}日(?:.*)?", title_candidate) and
                not re.fullmatch(r"^『.*』の番組エピソードです$", title_candidate) and
                _normalize_punct(title_candidate) != _normalize_punct(name)):
                
                # 必要に応じて番組名が含まれている場合は除去する
                try:
                    pattern = re.escape(name).replace("\\!", "[!！]")
                    cleaned = re.sub(pattern, "", title_candidate).strip()
                except re.error:
                    cleaned = title_candidate.replace(name, "").strip()
                
                final_title = cleaned if (cleaned and len(cleaned) > 0) else title_candidate
                return prog_name_candidate, final_title

        # 要素数が2つ以下、または上記条件に該当しなかった場合は従来のロジックを実行
        for text in p_texts:
            if not text or _normalize_punct(text) == _normalize_punct(name):
                continue
            if re.fullmatch(r"(?:\d{4}年)?\d{1,2}月\d{1,2}日(?:.*)?", text):
                continue
            if re.fullmatch(r"^『.*』の番組エピソードです$", text):
                continue
            # テキスト内に番組名が含まれている場合は除去する
            try:
                pattern = re.escape(name).replace("\\!", "[!！]")
                cleaned = re.sub(pattern, "", text).strip()
            except re.error:
                cleaned = text.replace(name, "").strip()

            if cleaned and len(cleaned) > 0:
                return name, cleaned
            return name, text

        # 日付だけしかなければ日付をタイトル扱い
        for text in p_texts:
            if re.fullmatch(r"(?:\d{4}年)?\d{1,2}月\d{1,2}日", text):
                return name, text

        # ここまでで候補が見つからなければ、表示されている<p>のいずれかが
        # 番組名そのもの（句読点の差などを含む）か確認して、番組名を返す
        def _normalize(s: str) -> str:
            if not s:
                return s
            return s.replace("!", "！").replace("?", "？").replace(":", "：").strip()

        for text in p_texts:
            if _normalize(text) == _normalize(name):
                return text, ""

        return name, ""

    def _is_generic_detail_description(self, text: str) -> bool:
        if not text:
            return True
        text = text.strip()
        if re.fullmatch(r"^【NHK】.*番組エピソードです$", text):
            return True
        if re.fullmatch(r"^.*番組エピソードです$", text):
            return True
        return False

    def _extract_title_from_detail(self, dsoup, name: str) -> tuple[str, str]:
        # og:title -> title -> h1 の順で取得し、エピソードタイトルと番組名に分解する
        raw_title = ""
        for selector in [
            "meta[property='og:title']",
            "meta[name='title']",
        ]:
            tag = dsoup.select_one(selector)
            if tag:
                raw_title = tag.get("content", "").strip()
                if raw_title:
                    break

        if not raw_title:
            title_tag = dsoup.select_one("title")
            if title_tag:
                raw_title = title_tag.get_text(" ", strip=True)

        if not raw_title:
            heading = dsoup.select_one("h1")
            if heading:
                raw_title = heading.get_text(" ", strip=True)

        if raw_title:
            # NHK表記などを除去
            raw_title = re.sub(r"\s*[-–—|｜]\s*NHK.*$", "", raw_title)
            # 区切り文字で分割
            parts = re.split(r'\s*[-–—|｜]\s*', raw_title)
            # 空文字やNHKなどを除外
            parts = [p.strip() for p in parts if p.strip() and p.strip() not in ("NHK", "日本放送協会")]
            
            if len(parts) >= 2:
                # 設定された番組名 name が含まれるパーツを探す
                prog_part = None
                title_part = None
                def _norm(s: str) -> str:
                    return s.replace("!", "！").replace("?", "？").replace(":", "：")
                
                for p in parts:
                    if _norm(name) in _norm(p) or _norm(p) in _norm(name):
                        prog_part = p
                    else:
                        title_part = p
                
                # 分離できたらそれを返す
                if prog_part and title_part:
                    return prog_part, title_part.strip("「」『』 ")
                elif title_part:
                    return name, title_part.strip("「」『』 ")
                else:
                    return parts[0], parts[0]
            elif len(parts) == 1:
                # 分割できなかった場合は、name を除いてタイトルとする
                title_text = parts[0].replace(name, "").strip()
                title_text = title_text.strip("「」『』 ")
                if title_text:
                    return name, title_text
                return name, parts[0]

        # description を最後の手段とする
        for selector in [
            "meta[property='og:description']",
            "meta[name='description']",
        ]:
            tag = dsoup.select_one(selector)
            if tag:
                content = tag.get("content", "").strip()
                if content and not self._is_generic_detail_description(content):
                    return name, content[:50]

        return name, ""

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

            # タイトルと動的番組名の抽出
            prog_name_detected, title_candidate = self._extract_title_from_anchor(a_tag, name)
            if not title_candidate:
                title_candidate = text
                if "初回放送日" in text:
                    title_candidate = text.split("初回放送日")[0]

                # ノイズ除去
                title_candidate = re.sub(r"(?:\d{4}年)?\d{1,2}月\d{1,2}日.*$", "", title_candidate)
                title_candidate = re.sub(r"^\s*(?:\d+時間\s*)?(?:\d+分\s*)?(?:\d+秒\s*)?", "", title_candidate)
                title_candidate = title_candidate.replace(name, "").strip()
                title_candidate = title_candidate.strip("「」『』")

            if not prog_name_detected:
                prog_name_detected = name

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
                        prog_name_detected, title_candidate = self._extract_title_from_detail(detail_soup, name)
                        if not title_candidate.strip():
                            self.logger.warning(f"NHKタイトル抽出失敗 ({name}): {full_url}")
                    if not time_info or "-" not in time_info:
                        time_info = self._extract_time_from_detail(detail_soup, time_info)

            if not title_candidate.strip():
                title_candidate = "(タイトル未取得)"

            results.append(Episode(
                program_name=prog_name_detected,
                channel=channel,
                title=title_candidate,
                url=full_url,
                broadcast_time=time_info
            ))

        return results
