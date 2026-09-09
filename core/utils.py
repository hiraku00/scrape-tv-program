import re
import unicodedata
from datetime import datetime
from typing import List, Tuple

from core.models import Episode

# X/Twitter の公称上限は 280 だが、API投稿で弾かれないよう安全マージンを取る
TWEET_MAX_LENGTH = 276
URL_CHAR_WEIGHT = 23
WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]

def get_display_width(text: str) -> int:
    """文字列の表示幅（全角2、半角1）を計算する"""
    width = 0
    for char in text:
        if unicodedata.east_asian_width(char) in ('F', 'W', 'A'):
            width += 2
        else:
            width += 1
    return width

def count_tweet_length(text: str) -> int:
    """Twitter仕様での文字数カウント（URL=23文字、全角2、半角1）"""
    url_pattern = re.compile(r'https?://\S+')
    urls = url_pattern.findall(text)
    text_without_urls = url_pattern.sub('', text)
    text_length = get_display_width(text_without_urls)
    total_length = text_length + (URL_CHAR_WEIGHT * len(urls))
    return total_length

def convert_jp_ampm_to_24h(time_str: str) -> str:
    """「午前/午後」表記の時刻を24時間表記に変換する（変換できなければそのまま返す）"""
    m = re.match(r"(午前|午後)(\d{1,2}):(\d{2})", time_str.strip())
    if not m:
        return time_str
    ampm, h, m_str = m.group(1), int(m.group(2)), m.group(3)
    if ampm == "午後" and h < 12:
        h += 12
    elif ampm == "午前" and h == 12:
        h = 0
    return f"{h:02d}:{m_str}"


def pad_text(text: str, target_width: int) -> str:
    """表示幅に合わせてスペースでパディングする"""
    current_width = get_display_width(text)
    padding = max(0, target_width - current_width)
    return text + (" " * padding)

def split_program_block(block_text: str, header_text: str = "") -> list[str]:
    """1つの番組ブロックを文字数制限に収まるように分割する"""
    lines = block_text.strip().split('\n')
    if not lines:
        return []
    
    prog_header = lines[0] # ●番組名...
    items = []
    # 1アイテム = タイトル行 + URL行
    for i in range(1, len(lines), 2):
        if i + 1 < len(lines):
            items.append(f"{lines[i]}\n{lines[i+1]}")
    
    split_tweets = []
    current_content = prog_header
    is_first = True
    
    # 初回ツイートには全体のヘッダー（日付等）が入るため制限を厳しくする
    header_len = count_tweet_length(header_text) if header_text else 0
    
    for item in items:
        item_text = f"\n{item}"
        current_len = count_tweet_length(current_content)
        item_len = count_tweet_length(item_text)
        
        limit = TWEET_MAX_LENGTH - (header_len if is_first else 0)
        
        if current_len + item_len <= limit:
            current_content += item_text
        else:
            # 限界を超えたので現在の分を保存
            split_tweets.append(current_content.strip())
            # 次のツイートを開始（ヘッダーは繰り返さず、直接アイテムから開始）
            current_content = item
            is_first = False
            
    if current_content:
        split_tweets.append(current_content.strip())

    return split_tweets


def build_header(target_dt: datetime) -> str:
    """投稿・出力の先頭に付ける日付ヘッダーを生成する"""
    weekday_ja = WEEKDAY_JA[target_dt.weekday()]
    return f"{target_dt.strftime('%y/%m/%d')}({weekday_ja})のニュース・ドキュメンタリー番組など\n\n"


def group_and_sort_episodes(episodes: List[Episode]) -> List[Tuple[Tuple[str, str, str], List[Episode]]]:
    """番組名・チャンネル・放送時間でグループ化し、放送時間の昇順に並べる"""
    grouped: dict[Tuple[str, str, str], List[Episode]] = {}
    for ep in episodes:
        key = (ep.program_name, ep.channel, ep.broadcast_time)
        bucket = grouped.setdefault(key, [])
        # 同じURLのエピソードは追加しない（重複排除）
        if any(e.url == ep.url for e in bucket):
            continue
        bucket.append(ep)

    return sorted(
        grouped.items(),
        key=lambda x: x[0][2].split('-')[0] if x[0][2] else "99:99"
    )


def build_blocks(
    sorted_items: List[Tuple[Tuple[str, str, str], List[Episode]]],
    overall_header: str,
) -> Tuple[List[str], List[str], bool]:
    """番組ごとのブロックを生成し、必要に応じて文字数制限で分割する

    戻り値: (分割前の生ブロック一覧, 分割後の最終ブロック一覧, 分割を実施したか)
    """
    raw_blocks = []
    final_blocks = []
    needs_split = False

    for i, ((name, channel, time), eps) in enumerate(sorted_items):
        time_str = f" {time}" if time else ""
        header = f"●{name}({channel}{time_str})"
        block_lines = [header]
        for ep in eps:
            block_lines.append(f"・{ep.title}")
            block_lines.append(ep.url)
        block_text = "\n".join(block_lines)
        raw_blocks.append(block_text)

        # 最初のブロックだけ全体のヘッダー長を考慮
        header_to_consider = overall_header if i == 0 else ""

        if count_tweet_length(header_to_consider + block_text) > TWEET_MAX_LENGTH:
            final_blocks.extend(split_program_block(block_text, header_to_consider))
            needs_split = True
        else:
            final_blocks.append(block_text)

    return raw_blocks, final_blocks, needs_split
