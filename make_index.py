import sys
sys.stdout.reconfigure(encoding="utf-8")
import json
from pathlib import Path

MD_DIR = Path(r"C:\Users\s28790\Downloads\AILEAD_pack_extracted\AILEAD_pack")
OUT_FILE = Path(r"C:\Users\s28790\.ms-ad\ailead_rag\logs_index.json")

files_data = []
md_files = list(MD_DIR.glob("*.md"))
print(f"{len(md_files)} 件のファイルを処理中...")

for f in md_files:
    try:
        content = f.read_text(encoding="utf-8", errors="replace")
        files_data.append({
            "filename": f.name,
            "content": content[:3000]
        })
    except Exception as e:
        print(f"スキップ: {f.name} ({e})")

with open(OUT_FILE, "w", encoding="utf-8") as fp:
    json.dump(files_data, fp, ensure_ascii=False)

print(f"完了！{len(files_data)} 件 → {OUT_FILE}")
