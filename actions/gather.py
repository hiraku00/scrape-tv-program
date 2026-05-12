import json
import os
from datetime import datetime
from pathlib import Path
from core.logger import setup_logger
from scrapers.nhk import NHKScraper
from scrapers.tvtokyo import TVTokyoScraper
from scrapers.twitter_scraper import TwitterScraper

def run_gather(target_date_str: str):
    logger = setup_logger("gather")
    target_date = datetime.strptime(target_date_str, "%Y%m%d")
    
    config_path = Path(__file__).parent.parent / "config" / "programs.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    logger.info(f"=== 情報収集開始 ({target_date_str}) ===")
    import time
    global_start = time.time()
    
    episodes = []
    total_count = len(config["nhk"]) + len(config["tvtokyo"]) + 1
    current_idx = 1
    
    # 1. NHK Web
    nhk_scraper = NHKScraper(config["nhk"])
    episodes.extend(nhk_scraper.scrape(target_date, global_start, current_idx, total_count))
    current_idx += len(config["nhk"])
    
    # 2. TV Tokyo Web
    tv_scraper = TVTokyoScraper(config["tvtokyo"])
    episodes.extend(tv_scraper.scrape(target_date, global_start, current_idx, total_count))
    current_idx += len(config["tvtokyo"])
    
    # 3. Twitter
    twitter_scraper = TwitterScraper(config["twitter"])
    episodes.extend(twitter_scraper.scrape(target_date, global_start, current_idx, total_count))
    
    if not episodes:
        logger.warning("取得できたエピソードはありませんでした。")
        return
        
    # 重複排除とグループ化
    grouped = {}
    for ep in episodes:
        # キー: (番組名, チャンネル, 放送時間)
        key = (ep.program_name, ep.channel, ep.broadcast_time)
        if key not in grouped:
            grouped[key] = []
        # 同じURLのエピソードは追加しない（重複排除）
        if any(e.url == ep.url for e in grouped[key]):
            continue
        grouped[key].append(ep)
        
    # 放送時間の昇順でソート（時間が空の場合は最後に配置）
    sorted_items = sorted(
        grouped.items(),
        key=lambda x: x[0][2].split('-')[0] if x[0][2] else "99:99"
    )
    
    from core.utils import split_program_block, count_tweet_length
    
    # 投稿用ヘッダー（日付）を考慮した分割
    target_dt = datetime.strptime(target_date_str, "%Y%m%d")
    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"][target_dt.weekday()]
    overall_header = f"{target_dt.strftime('%y/%m/%d')}({weekday_ja})のニュース・ドキュメンタリー番組など\n\n"
    
    output_blocks = [] # 分割前の生ブロックを保持
    final_output_blocks = []
    needs_split_backup = False
    
    # 1. 各番組ごとのブロックを生成
    for i, ((name, channel, time), eps) in enumerate(sorted_items):
        time_str = f" {time}" if time else ""
        header = f"●{name}({channel}{time_str})"
        block_lines = [header]
        for ep in eps:
            block_lines.append(f"・{ep.title}")
            block_lines.append(ep.url)
        block_text = "\n".join(block_lines)
        output_blocks.append(block_text)
        
        # 2. 分割が必要かチェック
        # 最初のブロックだけ全体のヘッダー長を考慮
        header_to_consider = overall_header if i == 0 else ""
        
        if count_tweet_length(header_to_consider + block_text) > 280:
            split_sub_blocks = split_program_block(block_text, header_to_consider)
            final_output_blocks.extend(split_sub_blocks)
            needs_split_backup = True
        else:
            final_output_blocks.append(block_text)
        
    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    
    # メインファイルとバックアップファイルのパス
    out_file = out_dir / f"{target_date_str}.txt"
    before_split_file = out_dir / f"{target_date_str}.raw.txt"
    
    # 1. まず「分割前の生データ」を保存（常に最新の生データを保持）
    if needs_split_backup:
        with open(before_split_file, "w", encoding="utf-8") as f:
            # 元の output_blocks (未分割) を書き出し
            f.write("\n\n".join(output_blocks) + "\n")
        logger.info(f"生データを保存しました: {before_split_file.name}")
    elif before_split_file.exists():
        # 分割が不要な場合は、前回の残骸があれば削除するか、.bak にリネーム
        before_split_file.unlink()

    # 2. メインファイル（分割済み）を保存
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n\n".join(final_output_blocks) + "\n")
        
    status_msg = f"{len(episodes)}件を {out_file.name} に保存しました"
    if needs_split_backup:
        status_msg += f" (自動分割実施。生データは {before_split_file.name})"
    logger.info(f"=== 情報収集完了: {status_msg} ===")
