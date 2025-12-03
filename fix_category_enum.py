"""
批量修復 CategoryEnum.OUTERWEAR -> CategoryEnum.OUTER
"""
import os
import re
from pathlib import Path

# 要修復的目錄
base_dir = Path(__file__).parent / "app"

# 要搜尋的檔案類型
file_patterns = ["*.py"]

# 修復計數
fixed_files = []
total_replacements = 0

def fix_file(file_path):
    """修復單個檔案"""
    global total_replacements
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 檢查是否包含 CategoryEnum.OUTERWEAR
        if 'CategoryEnum.OUTERWEAR' not in content:
            return False
        
        # 替換
        new_content = content.replace('CategoryEnum.OUTERWEAR', 'CategoryEnum.OUTER')
        
        # 計算替換次數
        count = content.count('CategoryEnum.OUTERWEAR')
        total_replacements += count
        
        # 寫回檔案
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"[OK] 修復: {file_path.relative_to(base_dir.parent)} ({count} 處)")
        return True
        
    except Exception as e:
        print(f"[ERROR] 錯誤: {file_path} - {e}")
        return False

def main():
    """主函數"""
    print("開始搜尋需要修復的檔案...\n")
    
    # 遍歷所有 Python 檔案
    for py_file in base_dir.rglob("*.py"):
        if fix_file(py_file):
            fixed_files.append(py_file)
    
    # 顯示結果
    print(f"\n{'='*60}")
    print(f"修復完成！")
    print(f"   修復檔案數: {len(fixed_files)}")
    print(f"   總替換次數: {total_replacements}")
    print(f"{'='*60}\n")
    
    if fixed_files:
        print("修復的檔案列表:")
        for f in fixed_files:
            print(f"  - {f.relative_to(base_dir.parent)}")

if __name__ == "__main__":
    main()
