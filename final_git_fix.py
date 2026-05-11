import subprocess

def run_git(args):
    cmd = ["/usr/local/bin/git"] + args
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
    else:
        print(f"Success: {result.stdout}")
    return result

def main():
    # 1. インデックスのクリア（.gitignore を反映させるため）
    run_git(["rm", "-r", "--cached", "."])
    
    # 2. output/ を含む全ファイルをステージング
    run_git(["add", "."])
    
    # 3. text-tube 等のスタイルを完全に踏襲したコミットメッセージ
    commit_message = "chore(git): __pycache__ の追跡を解除し、記録用として output/ を管理対象に追加"
    run_git(["commit", "-m", commit_message])
    
    # 4. GitHubへのプッシュ
    print("GitHubへ反映しています...")
    run_git(["push", "origin", "main"])

if __name__ == "__main__":
    main()
