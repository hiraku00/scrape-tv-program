import re
import unicodedata

# Twitterの文字数制限（半角280/全角140）
TWEET_MAX_LENGTH = 280
URL_CHAR_WEIGHT = 23

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
