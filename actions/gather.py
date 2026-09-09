import json
import os
import time
from datetime import datetime
from pathlib import Path
from core.logger import setup_logger
from core.utils import build_header, build_blocks, group_and_sort_episodes
from scrapers.nhk import NHKScraper
from scrapers.bstbs import BSTBSScraper
from scrapers.tvtokyo import TVTokyoScraper
from scrapers.twitter_scraper import TwitterScraper

def run_gather(target_date_str: str):
    logger = setup_logger("gather")
    target_date = datetime.strptime(target_date_str, "%Y%m%d")
    
    config_path = Path(__file__).parent.parent / "config" / "programs.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    logger.info(f"=== 情報収集開始 ({target_date_str}) ===")
    global_start = time.time()
    
    episodes = []
    total_count = len(config["nhk"]) + len(config["bstbs"]) + len(config["tvtokyo"]) + 1
    current_idx = 1
    
    # 1. NHK Web
    nhk_scraper = NHKScraper(config["nhk"])
    episodes.extend(nhk_scraper.scrape(target_date, global_start, current_idx, total_count))
    current_idx += len(config["nhk"])

    # 2. BS-TBS Web
    bstbs_scraper = BSTBSScraper(config["bstbs"])
    episodes.extend(bstbs_scraper.scrape(target_date, global_start, current_idx, total_count))
    current_idx += len(config["bstbs"])
    
    # 3. TV Tokyo Web
    tv_scraper = TVTokyoScraper(config["tvtokyo"])
    episodes.extend(tv_scraper.scrape(target_date, global_start, current_idx, total_count))
    current_idx += len(config["tvtokyo"])
    
    # 4. Twitter
    twitter_scraper = TwitterScraper(config["twitter"])
    episodes.extend(twitter_scraper.scrape(target_date, global_start, current_idx, total_count))
    
    if not episodes:
        logger.warning("取得できたエピソードはありませんでした。")
        return
        
    # 重複排除とグループ化、放送時間の昇順でソート（時間が空の場合は最後に配置）
    sorted_items = group_and_sort_episodes(episodes)

    target_dt = datetime.strptime(target_date_str, "%Y%m%d")
    overall_header = build_header(target_dt)

    output_blocks, final_output_blocks, needs_split_backup = build_blocks(sorted_items, overall_header)

    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(exist_ok=True)

    out_file = out_dir / f"{target_date_str}.txt"
    before_split_file = out_dir / f"{target_date_str}.raw.txt"

    # 1. まず「分割前の生データ」を保存（常に最新の生データを保持）
    if needs_split_backup:
        with open(before_split_file, "w", encoding="utf-8") as f:
            # 元の output_blocks (未分割) を書き出し
            f.write(overall_header + "\n\n".join(output_blocks) + "\n")
        logger.info(f"生データを保存しました: {before_split_file.name}")
    elif before_split_file.exists():
        # 分割が不要な場合は、前回の残骸があれば削除するか、.bak にリネーム
        before_split_file.unlink()

    # 2. メインファイル（分割済み）を保存
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(overall_header + "\n\n".join(final_output_blocks) + "\n")

    status_msg = f"{len(episodes)}件を {out_file.name} に保存しました"
    if needs_split_backup:
        status_msg += f" (自動分割実施。生データは {before_split_file.name})"
    logger.info(f"=== 情報収集完了: {status_msg} ===")
