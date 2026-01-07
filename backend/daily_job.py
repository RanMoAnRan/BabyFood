import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone

import requests
from PIL import Image

from sources.nutrition_gov import fetch_recipe, list_recipe_slugs, map_tags


BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
RECIPES_DIR = os.path.join(DATA_DIR, "recipes")
IMAGES_DIR = os.path.join(DATA_DIR, "images")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def read_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def ensure_seed_data():
    os.makedirs(RECIPES_DIR, exist_ok=True)

    manifest_path = os.path.join(DATA_DIR, "manifest.json")
    index_path = os.path.join(DATA_DIR, "recipes_index.json")
    demo_detail_path = os.path.join(RECIPES_DIR, "demo_pumpkin_potato.json")

    if os.path.exists(manifest_path) and os.path.exists(index_path) and os.path.exists(demo_detail_path):
        return

    demo_id = "demo_pumpkin_potato"
    version = "seed-1"
    now = "2024-01-01T00:00:00Z"

    write_json(
        manifest_path,
        {
            "version": version,
            "updated_at": now,
            "recipe_count": 1,
            "latest_ids": [demo_id],
        },
    )

    write_json(
        index_path,
        {
            "version": version,
            "items": [
                {
                    "id": demo_id,
                    "title": "奶香南瓜土豆泥",
                    "min_age_month": 6,
                    "tags": ["6m+", "补锌", "通便", "早餐"],
                    "difficulty": 1,
                    "time_cost": 15,
                    "cover_image": "https://via.placeholder.com/800x600.png?text=BabyFood",
                    "publish_date": "2023-10-27",
                }
            ],
        },
    )

    write_json(
        demo_detail_path,
        {
            "id": demo_id,
            "title": "奶香南瓜土豆泥",
            "min_age_month": 6,
            "tags": ["6m+", "补锌", "通便", "早餐"],
            "difficulty": 1,
            "time_cost": 15,
            "cover_image": "https://via.placeholder.com/800x600.png?text=BabyFood",
            "nutrition_tip": "南瓜含有丰富的果胶，能保护胃肠道粘膜。",
            "ingredients": [
                {"name": "老南瓜", "amount": "30g"},
                {"name": "土豆", "amount": "50g"},
                {"name": "配方奶", "amount": "30ml"},
            ],
            "steps": [
                {
                    "step_index": 1,
                    "img": "https://via.placeholder.com/800x600.png?text=Step+1",
                    "text": "南瓜和土豆去皮切块，上锅蒸15分钟。",
                },
                {
                    "step_index": 2,
                    "img": "https://via.placeholder.com/800x600.png?text=Step+2",
                    "text": "倒入料理机，加入配方奶搅打细腻。",
                },
            ],
            "warnings": ["如果不甜可以不加糖", "1岁以内严禁加盐"],
            "source_url": "https://example.com/recipe/demo",
            "publish_date": "2023-10-27",
            "updated_at": now,
        },
    )


def parse_iso_date(date_str: str) -> str:
    if not date_str:
        return ""
    m = re.match(r"^\d{4}-\d{2}-\d{2}$", date_str)
    return date_str if m else ""


def infer_min_age_month(title: str, description: str, ingredients: list[dict], tags: list[str]) -> int:
    """
    Nutrition.gov 并不提供婴幼儿月龄字段。这里用非常保守的启发式规则做“可用的”月龄分布，
    仅用于让月龄导航在 MVP 阶段可工作；上线前建议引入人工标注/专门辅食数据源。
    """
    text = " ".join(
        [
            title or "",
            description or "",
            " ".join([str(i.get("name", "")) for i in (ingredients or [])]),
            " ".join(tags or []),
        ]
    ).lower()

    puree_kw = ["puree", "purée", "mash", "mashed"]
    soft_kw = ["smoothie", "oatmeal", "porridge", "pudding", "yogurt", "dip", "soup", "stew", "broth"]
    complex_kw = [
        "salad",
        "sandwich",
        "burger",
        "pizza",
        "taco",
        "lasagna",
        "grilled",
        "roast",
        "chops",
        "steak",
        "muffin",
        "cookie",
        "cake",
        "sloppy",
    ]

    if any(k in text for k in puree_kw):
        return 6
    if any(k in text for k in soft_kw):
        return 8
    if any(k in text for k in complex_kw):
        return 12

    # 兜底：Nutrition.gov 的菜谱更偏“家庭菜”，默认 12m+
    return 12


def md5_file_name(url: str, ext: str) -> str:
    return f"{md5(url)}.{ext.lstrip('.')}"


def download_and_convert_cover(session: requests.Session, url: str, max_side: int = 1080, quality: int = 80) -> str:
    if not url:
        return ""
    os.makedirs(IMAGES_DIR, exist_ok=True)
    filename = md5_file_name(url, "webp")
    out_path = os.path.join(IMAGES_DIR, filename)
    if os.path.exists(out_path):
        return f"images/{filename}"

    res = session.get(url, timeout=30)
    res.raise_for_status()
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(res.content)

    img = Image.open(tmp_path)
    img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, max_side / max(w, h)) if max(w, h) > 0 else 1.0
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
    img.save(out_path, "webp", quality=quality, method=6)
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    return f"images/{filename}"


def build_nutrition_gov_data(limit: int | None, max_pages: int, download_images: bool) -> tuple[dict, dict, dict]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "BabyFoodBot/1.0 (+https://github.com/)",
            "Accept-Language": "en-US,en;q=0.8",
        }
    )

    slugs = list_recipe_slugs(session, max_pages=max_pages)
    if limit:
        slugs = slugs[:limit]

    items = []
    details_by_id = {}
    latest = []

    for slug in slugs:
        pr = fetch_recipe(session, slug)
        rid = md5(pr.source_url)

        cover = pr.cover_image_url
        if download_images and cover:
            cover = download_and_convert_cover(session, cover)

        tags = map_tags(pr.meal_types, pr.categories, pr.food_groups)
        min_age_month = infer_min_age_month(pr.title, pr.description, pr.ingredients, tags)

        publish_date = parse_iso_date(pr.publish_date) or "1970-01-01"
        time_cost = pr.prep_minutes if pr.prep_minutes is not None else 0

        index_item = {
            "id": rid,
            "title": pr.title,
            "min_age_month": min_age_month,
            "tags": tags,
            "difficulty": 1,
            "time_cost": time_cost,
            "cover_image": cover,
            "publish_date": publish_date,
        }
        items.append(index_item)

        tip = pr.description
        if len(tip) > 80:
            tip = tip[:80].rstrip() + "…"

        detail = {
            "id": rid,
            "title": pr.title,
            "min_age_month": min_age_month,
            "tags": tags,
            "difficulty": 1,
            "time_cost": time_cost,
            "cover_image": cover,
            "nutrition_tip": tip,
            "ingredients": pr.ingredients,
            "steps": [{"step_index": i + 1, "img": "", "text": t} for i, t in enumerate(pr.steps)],
            "warnings": [],
            "publish_date": publish_date,
            "updated_at": "",
            "source_url": pr.source_url,
            "origin_url": pr.origin_url,
            "source_name": "Nutrition.gov (USDA)",
        }
        details_by_id[rid] = detail
        latest.append((publish_date, rid))

    items.sort(key=lambda x: (x.get("publish_date", ""), x.get("title", "")), reverse=True)

    # latest_ids: newest publish_date first
    latest.sort(reverse=True)
    latest_ids = [rid for _, rid in latest[:10]]

    manifest = {
        "version": "",
        "updated_at": "",
        "recipe_count": len(items),
        "latest_ids": latest_ids,
        "source": {
            "name": "Nutrition.gov (USDA)",
            "base_url": "https://www.nutrition.gov/recipes/search",
            "note": "USDA/NAL 站点内容一般为 public domain，但仍建议保留 source_url/origin_url 以便溯源。",
        },
    }

    index = {"version": "", "items": items}
    return manifest, index, details_by_id


def main():
    """
    这是一个“可运行的脚手架”：
    - v1：先保证 data 目录产物齐全（方便小程序/CDN联调）
    - 后续：替换为真实抓取逻辑（目标站解析、图片下载压缩、去重、增量写入等）
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="nutrition_gov", choices=["nutrition_gov"])
    parser.add_argument("--limit", type=int, default=0, help="仅抓取前 N 条（0 表示全量）")
    parser.add_argument("--max-pages", type=int, default=20, help="最多翻页数（每页 24 条）")
    parser.add_argument("--no-images", action="store_true", help="跳过图片下载（调试用）")
    parser.add_argument("--dry-run", action="store_true", help="只抓取与解析，不落盘写文件")
    args = parser.parse_args()

    ensure_seed_data()

    manifest_path = os.path.join(DATA_DIR, "manifest.json")
    index_path = os.path.join(DATA_DIR, "recipes_index.json")

    old_manifest = read_json(manifest_path, {})
    old_index = read_json(index_path, {})

    limit = args.limit or None
    download_images = not args.no_images

    if args.site == "nutrition_gov":
        new_manifest, new_index, details = build_nutrition_gov_data(
            limit=limit, max_pages=args.max_pages, download_images=download_images
        )
    else:
        raise SystemExit(f"unsupported site: {args.site}")

    if args.dry_run:
        print("dry-run:", args.site, "recipes =", len(new_index["items"]))
        if new_index["items"]:
            print("sample:", new_index["items"][0]["title"])
        return

    changed = False
    old_items = old_index.get("items") if isinstance(old_index, dict) else None
    if old_items != new_index["items"]:
        changed = True

    # manifest 的内容变化也应触发写盘（例如 latest_ids 数量调整）
    if isinstance(old_manifest, dict):
        old_m = dict(old_manifest)
        new_m = dict(new_manifest)
        old_m.pop("version", None)
        old_m.pop("updated_at", None)
        new_m.pop("version", None)
        new_m.pop("updated_at", None)
        if old_m != new_m:
            changed = True

    # 逐条对比详情，避免仅详情变化却误判为“无变化”
    now = utc_now_iso()
    for rid, detail in details.items():
        detail_path = os.path.join(RECIPES_DIR, f"{rid}.json")
        old_detail = read_json(detail_path, None) if os.path.exists(detail_path) else None
        if not isinstance(old_detail, dict):
            detail["updated_at"] = now
            changed = True
            continue

        old_copy = dict(old_detail)
        new_copy = dict(detail)
        old_copy.pop("updated_at", None)
        new_copy.pop("updated_at", None)
        if old_copy == new_copy:
            detail["updated_at"] = old_detail.get("updated_at") or ""
        else:
            detail["updated_at"] = now
            changed = True

    if not changed:
        print("No changes. Skip writing.")
        return

    version = os.environ.get("DATA_VERSION") or utc_now_iso()
    new_manifest["version"] = version
    new_index["version"] = version
    new_manifest["updated_at"] = utc_now_iso()

    write_json(manifest_path, new_manifest)
    write_json(index_path, new_index)

    for rid, detail in details.items():
        detail_path = os.path.join(RECIPES_DIR, f"{rid}.json")
        write_json(detail_path, detail)

    print("daily_job.py finished. recipes =", len(new_index["items"]), "version =", version)


if __name__ == "__main__":
    main()
