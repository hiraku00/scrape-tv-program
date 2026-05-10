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
    
    output_blocks = []
    for (name, channel, time), eps in sorted_items:
        time_str = f" {time}" if time else ""
        header = f"●{name}({channel}{time_str})"
        block_lines = [header]
        for ep in eps:
            block_lines.append(f"・{ep.title}")
            block_lines.append(ep.url)
        output_blocks.append("\n".join(block_lines))
        
    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    
    # メインファイル（マージ・ソート済み）を保存
    out_file = out_dir / f"{target_date_str}.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n\n".join(output_blocks) + "\n")
        
    logger.info(f"=== 情報収集完了: {len(episodes)}件を {out_file.name} に保存しました ===")
