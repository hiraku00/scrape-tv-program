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
    # 1. すべてのインデックスを一旦削除（ファイルは消えません）
    # これにより .gitignore が正しく再適用されます
    run_git(["rm", "-r", "--cached", "."])
    
    # 2. .gitignore に従って必要なファイルだけを再追加
    run_git(["add", "."])
    
    # 3. コミット
    run_git(["commit", "-m", "fix: remove __pycache__ from git tracking and apply .gitignore correctly"])
    
    # 4. プッシュ
    print("Pushing fixes to GitHub...")
    run_git(["push", "origin", "main"])

if __name__ == "__main__":
    main()
