import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone

import requests
from PIL import Image

from sources import myplate_gov, nutrition_gov
try:
    from utils.translator import translate_text
except Exception:  # pragma: no cover
    translate_text = None


BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
RECIPES_DIR = os.path.join(DATA_DIR, "recipes")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

_RE_CHINESE = re.compile(r"[\u4e00-\u9fff]")
_RE_ASCII_LETTER = re.compile(r"[A-Za-z]")


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


def has_chinese(text: str) -> bool:
    return bool(_RE_CHINESE.search(text or ""))


def needs_translation(text: str) -> bool:
    if not text:
        return False
    return bool(_RE_ASCII_LETTER.search(text)) and not has_chinese(text)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _translation_source(detail: dict) -> dict:
    ingredients = detail.get("ingredients") if isinstance(detail, dict) else None
    steps = detail.get("steps") if isinstance(detail, dict) else None
    warnings = detail.get("warnings") if isinstance(detail, dict) else None

    if not isinstance(ingredients, list):
        ingredients = []
    if not isinstance(steps, list):
        steps = []
    if not isinstance(warnings, list):
        warnings = []

    return {
        "title": detail.get("title") or "",
        "nutrition_tip": detail.get("nutrition_tip") or "",
        "ingredients": [
            {"name": (i.get("name") or ""), "amount": (i.get("amount") or "")}
            for i in ingredients
            if isinstance(i, dict)
        ],
        "steps": [(s.get("text") or "") for s in steps if isinstance(s, dict)],
        "warnings": [str(w or "") for w in warnings],
    }


def _translation_source_hash(detail: dict) -> str:
    raw = json.dumps(_translation_source(detail), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return md5(raw)


def _parse_translated_tokens(translated: str, tokens: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if not translated or not tokens:
        return out
    for i, token in enumerate(tokens):
        start = translated.find(token)
        if start < 0:
            continue
        start += len(token)
        while start < len(translated) and translated[start] in " \t\r\n:：-—–":
            start += 1

        end = len(translated)
        for j in range(i + 1, len(tokens)):
            nxt = translated.find(tokens[j], start)
            if nxt >= 0:
                end = nxt
                break
        out[token] = translated[start:end].strip()
    return out


def _translate_detail_inplace(
    detail: dict,
    *,
    title_zh: str | None,
    do_translate: bool,
    old_detail: dict | None,
):
    """
    将详情中的可见文本翻译为中文（最佳努力），并写入 `_translation` 元信息用于增量复用。
    """
    if not isinstance(detail, dict):
        return

    src_hash = _translation_source_hash(detail)
    new_meta = {"dest": "zh-CN", "source_hash": src_hash, "translated": False}

    # 始终用列表页标题（若有）覆盖详情标题，避免不一致
    if title_zh:
        detail["title"] = title_zh

    # 复用旧翻译：同一份英文源数据 + 已翻译成功，则直接沿用旧的中文字段
    if do_translate and isinstance(old_detail, dict):
        old_meta = old_detail.get("_translation")
        if (
            isinstance(old_meta, dict)
            and old_meta.get("dest") == "zh-CN"
            and old_meta.get("source_hash") == src_hash
            and old_meta.get("translated") is True
        ):
            if not title_zh and old_detail.get("title"):
                detail["title"] = old_detail.get("title")
            if old_detail.get("nutrition_tip") is not None:
                detail["nutrition_tip"] = old_detail.get("nutrition_tip") or ""

            old_ings = old_detail.get("ingredients")
            new_ings = detail.get("ingredients")
            if isinstance(old_ings, list) and isinstance(new_ings, list) and len(old_ings) == len(new_ings):
                for o, n in zip(old_ings, new_ings):
                    if isinstance(o, dict) and isinstance(n, dict):
                        if o.get("name") is not None:
                            n["name"] = o.get("name") or ""
                        if o.get("amount") is not None:
                            n["amount"] = o.get("amount") or ""

            old_steps = old_detail.get("steps")
            new_steps = detail.get("steps")
            if isinstance(old_steps, list) and isinstance(new_steps, list) and len(old_steps) == len(new_steps):
                for o, n in zip(old_steps, new_steps):
                    if isinstance(o, dict) and isinstance(n, dict) and o.get("text") is not None:
                        n["text"] = o.get("text") or ""

            if isinstance(old_detail.get("warnings"), list):
                detail["warnings"] = old_detail.get("warnings") or []

            new_meta["translated"] = True
            detail["_translation"] = new_meta
            return

    # 不启用翻译 / 缺少依赖
    if not do_translate or translate_text is None:
        detail["_translation"] = new_meta
        return

    # 构造带 token 的块文本，尽量一次请求翻译，避免大量调用导致限流
    token_pairs: list[tuple[str, str]] = []
    token_pairs.append(("[[BF_TITLE]]", _collapse_ws(detail.get("title") or "")))
    token_pairs.append(("[[BF_TIP]]", _collapse_ws(detail.get("nutrition_tip") or "")))

    ingredients = detail.get("ingredients")
    if isinstance(ingredients, list):
        for i, ing in enumerate(ingredients):
            if not isinstance(ing, dict):
                continue
            token_pairs.append((f"[[BF_ING_NAME_{i}]]", _collapse_ws(ing.get("name") or "")))
            token_pairs.append((f"[[BF_ING_AMOUNT_{i}]]", _collapse_ws(ing.get("amount") or "")))

    steps = detail.get("steps")
    if isinstance(steps, list):
        for i, st in enumerate(steps):
            if not isinstance(st, dict):
                continue
            token_pairs.append((f"[[BF_STEP_{i}]]", _collapse_ws(st.get("text") or "")))

    warnings = detail.get("warnings")
    if isinstance(warnings, list):
        for i, w in enumerate(warnings):
            token_pairs.append((f"[[BF_WARN_{i}]]", _collapse_ws(w or "")))

    # 若无需翻译（已经是中文/无英文内容），标记为已翻译以便后续跳过
    needs = [t for t, txt in token_pairs if t != "[[BF_TITLE]]" and needs_translation(txt)]
    if not needs:
        new_meta["translated"] = True
        detail["_translation"] = new_meta
        return

    block = "\n".join(f"{t} {txt}" for t, txt in token_pairs)
    zh_block = translate_text(block, dest="zh-CN")
    tokens = [t for t, _ in token_pairs]
    parsed = _parse_translated_tokens(zh_block, tokens)

    # 应用翻译结果（缺失则回退为原文）
    if not title_zh:
        detail["title"] = parsed.get("[[BF_TITLE]]") or detail.get("title") or ""
    detail["nutrition_tip"] = parsed.get("[[BF_TIP]]") or detail.get("nutrition_tip") or ""

    if isinstance(ingredients, list):
        for i, ing in enumerate(ingredients):
            if not isinstance(ing, dict):
                continue
            ing["name"] = parsed.get(f"[[BF_ING_NAME_{i}]]") or ing.get("name") or ""
            ing["amount"] = parsed.get(f"[[BF_ING_AMOUNT_{i}]]") or ing.get("amount") or ""

    if isinstance(steps, list):
        for i, st in enumerate(steps):
            if not isinstance(st, dict):
                continue
            st["text"] = parsed.get(f"[[BF_STEP_{i}]]") or st.get("text") or ""

    if isinstance(warnings, list):
        out_warns = []
        for i, w in enumerate(warnings):
            out_warns.append(parsed.get(f"[[BF_WARN_{i}]]") or w or "")
        detail["warnings"] = out_warns

    translated_cnt = 0
    for token in needs:
        if has_chinese(parsed.get(token) or ""):
            translated_cnt += 1
    new_meta["translated"] = translated_cnt >= max(1, (len(needs) + 1) // 2)
    detail["_translation"] = new_meta


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


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "BabyFoodBot/1.0 (+https://github.com/)",
            "Accept-Language": "en-US,en;q=0.8",
        }
    )
    return session


def build_nutrition_gov_data(
    limit: int | None,
    max_pages: int,
    download_images: bool,
    *,
    verbose: bool = False,
) -> tuple[dict, dict, dict]:
    session = new_session()

    print(f"[nutrition_gov] 列表抓取中… max_pages={max_pages}", flush=True)
    slugs = nutrition_gov.list_recipe_slugs(session, max_pages=max_pages)
    if limit:
        slugs = slugs[:limit]
    print(f"[nutrition_gov] 获取到 {len(slugs)} 条 recipe 入口", flush=True)

    items = []
    details_by_id = {}
    latest = []

    for slug in slugs:
        i = len(items) + 1
        total = len(slugs)
        if verbose or total <= 10 or i == 1 or i == total or i % 20 == 0:
            print(f"[nutrition_gov] 抓取详情 {i}/{total}: {slug}", flush=True)
        try:
            pr = nutrition_gov.fetch_recipe(session, slug)
        except Exception as e:
            print(f"warn: nutrition_gov fetch failed: {slug}: {e}")
            continue
        rid = md5(pr.source_url)

        cover = pr.cover_image_url
        if download_images and cover:
            cover = download_and_convert_cover(session, cover)

        tags = nutrition_gov.map_tags(pr.meal_types, pr.categories, pr.food_groups)
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
            "source_name": "Nutrition.gov (USDA)",
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

    print(f"[nutrition_gov] 解析完成：{len(items)} 条", flush=True)

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


def build_myplate_gov_data(
    limit: int | None,
    max_pages: int,
    download_images: bool,
    *,
    verbose: bool = False,
) -> tuple[dict, dict, dict]:
    session = new_session()

    print(f"[myplate_gov] 列表抓取中… max_pages={max_pages}", flush=True)
    slugs = myplate_gov.list_recipe_slugs(session, max_pages=max_pages, verbose=verbose)
    if limit:
        slugs = slugs[:limit]
    print(f"[myplate_gov] 获取到 {len(slugs)} 条 recipe 入口", flush=True)
    if not slugs:
        print("[myplate_gov] 提示：若持续为 0，多半是 www.myplate.gov 访问超时/被拦；可加 --verbose 看具体失败原因。", flush=True)

    items = []
    details_by_id = {}
    latest = []

    for slug in slugs:
        i = len(items) + 1
        total = len(slugs)
        if verbose or total <= 10 or i == 1 or i == total or i % 20 == 0:
            print(f"[myplate_gov] 抓取详情 {i}/{total}: {slug}", flush=True)
        try:
            pr = myplate_gov.fetch_recipe(session, slug)
        except Exception as e:
            print(f"warn: myplate_gov fetch failed: {slug}: {e}")
            continue
        rid = md5(pr.source_url)

        cover = pr.cover_image_url
        if download_images and cover:
            cover = download_and_convert_cover(session, cover)

        tags = myplate_gov.map_tags(pr.meal_types, pr.categories, pr.food_groups)
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
            "source_name": "MyPlate Kitchen (USDA)",
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
            "source_name": "MyPlate Kitchen (USDA)",
        }
        details_by_id[rid] = detail
        latest.append((publish_date, rid))

    items.sort(key=lambda x: (x.get("publish_date", ""), x.get("title", "")), reverse=True)

    latest.sort(reverse=True)
    latest_ids = [rid for _, rid in latest[:10]]

    print(f"[myplate_gov] 解析完成：{len(items)} 条", flush=True)

    manifest = {
        "version": "",
        "updated_at": "",
        "recipe_count": len(items),
        "latest_ids": latest_ids,
        "source": {
            "name": "MyPlate Kitchen (USDA)",
            "base_url": "https://www.myplate.gov/myplate-kitchen/recipes",
            "note": "MyPlate.gov 为 USDA 站点；上线前建议保留 source_url/origin_url 并核对可再分发范围。",
        },
    }

    index = {"version": "", "items": items}
    return manifest, index, details_by_id


def build_all_data(
    limit: int | None,
    max_pages: int,
    download_images: bool,
    *,
    verbose: bool = False,
) -> tuple[dict, dict, dict]:
    items: list[dict] = []
    details_by_id: dict[str, dict] = {}
    sources: list[dict] = []

    remaining = limit
    build_fns = [
        ("nutrition_gov", build_nutrition_gov_data),
        ("myplate_gov", build_myplate_gov_data),
    ]

    for name, fn in build_fns:
        src_limit = remaining if remaining is not None else None
        try:
            src_manifest, src_index, src_details = fn(
                limit=src_limit,
                max_pages=max_pages,
                download_images=download_images,
                verbose=verbose,
            )
        except Exception as e:
            print(f"warn: skip {name}: {e}")
            continue

        src = src_manifest.get("source")
        if isinstance(src, dict):
            sources.append(src)

        if isinstance(src_index, dict) and isinstance(src_index.get("items"), list):
            items.extend(src_index["items"])

        if isinstance(src_details, dict):
            for rid, detail in src_details.items():
                if rid in details_by_id:
                    continue
                details_by_id[rid] = detail

        if remaining is not None:
            remaining = max(0, remaining - int(src_manifest.get("recipe_count") or 0))
            if remaining <= 0:
                break

    items.sort(key=lambda x: (x.get("publish_date", ""), x.get("title", "")), reverse=True)

    deduped: list[dict] = []
    seen_ids = set()
    for it in items:
        rid = it.get("id") if isinstance(it, dict) else None
        if not rid:
            continue
        rid = str(rid)
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        deduped.append(it)
    items = deduped

    latest_ids = [it.get("id") for it in items[:10] if it and it.get("id")]

    print(f"[all] 合并完成：{len(items)} 条", flush=True)

    manifest = {
        "version": "",
        "updated_at": "",
        "recipe_count": len(items),
        "latest_ids": latest_ids,
        "sources": sources,
        "source": (
            sources[0]
            if len(sources) == 1
            else {
                "name": "Nutrition.gov + MyPlate Kitchen (USDA)",
                "base_url": "",
                "note": "聚合多个 USDA 站点数据；建议保留 source_url/origin_url 以便溯源与合规核对。",
            }
        ),
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
    parser.add_argument("--site", default="all", choices=["all", "nutrition_gov", "myplate_gov"])
    parser.add_argument("--limit", type=int, default=0, help="仅抓取前 N 条（0 表示全量）")
    parser.add_argument("--max-pages", type=int, default=20, help="最多翻页数（每页 24 条）")
    parser.add_argument("--no-images", action="store_true", help="跳过图片下载（调试用）")
    parser.add_argument("--no-translate", action="store_true", help="跳过中文翻译（默认会翻译详情文本）")
    parser.add_argument("--verbose", action="store_true", help="打印抓取进度")
    parser.add_argument("--dry-run", action="store_true", help="只抓取与解析，不落盘写文件")
    args = parser.parse_args()

    print(
        f"run: site={args.site} limit={args.limit or 0} max_pages={args.max_pages} "
        f"images={'off' if args.no_images else 'on'} translate={'off' if args.no_translate else 'on'} "
        f"dry_run={'yes' if args.dry_run else 'no'}",
        flush=True,
    )

    ensure_seed_data()

    manifest_path = os.path.join(DATA_DIR, "manifest.json")
    index_path = os.path.join(DATA_DIR, "recipes_index.json")

    old_manifest = read_json(manifest_path, {})
    old_index = read_json(index_path, {})

    limit = args.limit or None
    download_images = not args.no_images

    if args.site == "nutrition_gov":
        new_manifest, new_index, details = build_nutrition_gov_data(
            limit=limit,
            max_pages=args.max_pages,
            download_images=download_images,
            verbose=args.verbose,
        )
    elif args.site == "myplate_gov":
        new_manifest, new_index, details = build_myplate_gov_data(
            limit=limit,
            max_pages=args.max_pages,
            download_images=download_images,
            verbose=args.verbose,
        )
    elif args.site == "all":
        new_manifest, new_index, details = build_all_data(
            limit=limit,
            max_pages=args.max_pages,
            download_images=download_images,
            verbose=args.verbose,
        )
    else:
        raise SystemExit(f"unsupported site: {args.site}")

    index_items = new_index.get("items") if isinstance(new_index, dict) and isinstance(new_index.get("items"), list) else []
    print(f"build: index_items={len(index_items)} details={len(details)}", flush=True)

    if args.dry_run:
        print("dry-run:", args.site, "recipes =", len(index_items))
        if index_items:
            print("sample:", index_items[0]["title"])
        return

    do_translate = not args.no_translate
    if do_translate and translate_text is None:
        print("translate disabled: missing translator dependency")
        do_translate = False
    print(f"translate: {'on' if do_translate else 'off'}", flush=True)

    # 列表标题：优先复用旧的中文标题，避免每天重复翻译导致的波动
    old_title_by_id: dict[str, str] = {}
    if isinstance(old_index, dict) and isinstance(old_index.get("items"), list):
        for it in old_index["items"]:
            if not isinstance(it, dict):
                continue
            rid = it.get("id")
            title = it.get("title")
            if rid and isinstance(title, str) and title:
                old_title_by_id[str(rid)] = title

    title_by_id: dict[str, str] = {}
    if isinstance(new_index, dict) and isinstance(new_index.get("items"), list):
        if do_translate:
            print(f"[translate] 列表标题处理：{len(new_index['items'])} 条", flush=True)

        for idx, it in enumerate(new_index["items"], start=1):
            if not isinstance(it, dict):
                continue
            rid = it.get("id")
            if not rid:
                continue
            rid = str(rid)
            title_en = str(it.get("title") or "")

            old_title = old_title_by_id.get(rid)
            if old_title and has_chinese(old_title):
                it["title"] = old_title
            elif do_translate and needs_translation(title_en):
                if args.verbose or len(new_index["items"]) <= 10 or idx == 1 or idx % 50 == 0:
                    print(f"[translate] 标题翻译 {idx}/{len(new_index['items'])}", flush=True)
                it["title"] = translate_text(title_en, dest="zh-CN")

            title_by_id[rid] = str(it.get("title") or "")

        # 标题翻译后重新排序，保证列表顺序稳定
        new_index["items"].sort(key=lambda x: (x.get("publish_date", ""), x.get("title", "")), reverse=True)

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
    total_details = len(details)
    print(f"[detail] 处理详情：{total_details} 条", flush=True)
    for idx, (rid, detail) in enumerate(details.items(), start=1):
        if args.verbose or total_details <= 10 or idx == 1 or idx == total_details or idx % 50 == 0:
            print(f"[detail] 进度 {idx}/{total_details}: {rid}", flush=True)
        detail_path = os.path.join(RECIPES_DIR, f"{rid}.json")
        old_detail = read_json(detail_path, None) if os.path.exists(detail_path) else None
        if do_translate:
            _translate_detail_inplace(
                detail,
                title_zh=title_by_id.get(rid) or None,
                do_translate=do_translate,
                old_detail=old_detail if isinstance(old_detail, dict) else None,
            )
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

    print(f"[write] 写入数据：manifest/index + {len(details)} 份详情", flush=True)
    write_json(manifest_path, new_manifest)
    write_json(index_path, new_index)

    for rid, detail in details.items():
        detail_path = os.path.join(RECIPES_DIR, f"{rid}.json")
        write_json(detail_path, detail)

    print("daily_job.py finished. recipes =", len(new_index["items"]), "version =", version)


if __name__ == "__main__":
    main()
