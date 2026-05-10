import webbrowser
import re
from pathlib import Path
from core.logger import setup_logger

def run_open(target_date_str: str):
    logger = setup_logger("open")
    
    out_dir = Path(__file__).parent.parent / "output"
    file_path = out_dir / f"{target_date_str}.txt"
    
    if not file_path.exists():
        logger.error(f"対象のファイルが見つかりません: {file_path}")
        return
        
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # URLを抽出
    urls = re.findall(r'https?://[^\s\n]+', content)
    
    if not urls:
        logger.warning("ファイル内にURLが見つかりませんでした。")
        return
        
    logger.info(f"=== {len(urls)} 件のURLをブラウザで開きます ===")
    
    for url in urls:
        logger.info(f"Opening: {url}")
        webbrowser.open(url)
        
    logger.info("✅ すべてのURLを開く処理が完了しました。")
