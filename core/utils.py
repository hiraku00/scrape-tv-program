import unicodedata

def get_display_width(text: str) -> int:
    """文字列の表示幅（全角2、半角1）を計算する"""
    width = 0
    for char in text:
        if unicodedata.east_asian_width(char) in ('F', 'W', 'A'):
            width += 2
        else:
            width += 1
    return width

def pad_text(text: str, target_width: int) -> str:
    """表示幅に合わせてスペースでパディングする"""
    current_width = get_display_width(text)
    padding = max(0, target_width - current_width)
    return text + (" " * padding)
