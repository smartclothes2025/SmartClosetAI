import json
import re
from pathlib import Path


def load_products_from_js(js_path: Path):
    """從 women.js / men.js 解析出 (id, image) 清單"""
    text = js_path.read_text(encoding="utf-8")
    # 粗略解析：在每個物件裡抓 id: X 和 image: "..."
    pattern = re.compile(r"\{\s*id:\s*(\d+)[^}]*?image:\s*\"([^\"]+)\"", re.DOTALL)
    products = []
    for m in pattern.finditer(text):
        pid = int(m.group(1))
        image = m.group(2)
        products.append({"id": pid, "image": image})
    print(f"[+] {js_path.name}: 解析 {len(products)} 筆商品")
    return products


def normalize_filename(image: str, prefix: str) -> str:
    """將 JS 內的 image 路徑轉成 config 用的 filename key"""
    if image.startswith(prefix):
        return image[len(prefix) :]
    return image


def main():
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "styleshop_images_config.json"
    output_path = base_dir / "styleshop_id_mapping.json"

    if not config_path.exists():
        raise SystemExit(f"找不到 styleshop_images_config.json: {config_path}")

    data = json.loads(config_path.read_text(encoding="utf-8"))
    images = data.get("images", {}) or {}

    # 網路商店 JS 位置：../網路商店/js/
    shop_dir = base_dir.parent / "網路商店" / "js"
    women_js = shop_dir / "women.js"
    men_js = shop_dir / "men.js"

    if not women_js.exists():
        raise SystemExit(f"找不到 women.js: {women_js}")
    if not men_js.exists():
        raise SystemExit(f"找不到 men.js: {men_js}")

    mapping = {"women": {}, "men": {}}
    warnings = []

    # 解析 women.js
    women_products = load_products_from_js(women_js)
    config_women = images.get("women", {}) or {}
    for p in women_products:
        rel = normalize_filename(p["image"], "模擬網路商家衣物圖片/女生/")
        if rel in config_women:
            mapping["women"][rel] = p["id"]
        else:
            warnings.append(f"[women] 找不到對應 config key: image={p['image']} -> rel={rel}")

    # 解析 men.js
    men_products = load_products_from_js(men_js)
    config_men = images.get("men", {}) or {}
    for p in men_products:
        rel = normalize_filename(p["image"], "模擬網路商家衣物圖片/男生/")
        if rel in config_men:
            mapping["men"][rel] = p["id"]
        else:
            warnings.append(f"[men] 找不到對應 config key: image={p['image']} -> rel={rel}")

    # 輸出 mapping 檔
    output_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] 已寫入 {output_path}")
    print(f"    women 對應筆數: {len(mapping['women'])}")
    print(f"    men 對應筆數:   {len(mapping['men'])}")

    if warnings:
        print("\n⚠ 以下圖片在 styleshop_images_config.json 中找不到對應 key，需要手動檢查:")
        for w in warnings:
            print("  -", w)


if __name__ == "__main__":
    main()
