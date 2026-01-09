"""Single-site importer for MyPlate Kitchen (MyPlate.gov) recipes."""

import json
import re
from dataclasses import dataclass
from typing import Iterable, Optional
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup


BASE = "https://www.myplate.gov"
SEARCH_URL = f"{BASE}/myplate-kitchen/recipes"


MEAL_MAP = {
    "Breakfast": "早餐",
    "Lunch": "午餐",
    "Dinner": "晚餐",
    "Snack": "小吃",
}

TAG_MAP = {
    "Kid-Friendly": "儿童友好",
    "30 Minutes or Less": "30分钟内",
    "Vegetables": "蔬菜",
    "Fruits": "水果",
    "Protein": "蛋白质",
    "Grains": "谷物",
    "Dairy": "乳制品",
    "Main Dish": "主菜",
    "Main Dishes": "主菜",
    "Side Dish": "配菜",
    "Side Dishes": "配菜",
    "Appetizer": "开胃菜",
    "Dessert": "甜品",
}


_RE_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _as_str_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if "," in raw:
            return [t for t in [_collapse_ws(p) for p in raw.split(",")] if t]
        return [_collapse_ws(raw)]
    if isinstance(value, dict):
        name = value.get("name")
        return [_collapse_ws(str(name))] if name else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_as_str_list(item))
        return [t for t in [_collapse_ws(x) for x in out] if t]
    return []


def _normalize_publish_date(value: str) -> str:
    s = _collapse_ws(value)
    if not s:
        return ""
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    if not m:
        return ""
    out = m.group(0)
    return out if _RE_ISO_DATE.match(out) else ""


def _parse_iso8601_duration_to_minutes(value: str) -> Optional[int]:
    """
    Parses ISO8601 duration like 'PT30M', 'PT1H', 'PT1H30M' to minutes.
    """
    s = _collapse_ws(value)
    if not s:
        return None
    m = re.match(r"^P(?:\d+Y)?(?:\d+M)?(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", s)
    if not m:
        return None
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    sec = int(m.group(3) or 0)
    return h * 60 + mins + (1 if sec >= 30 else 0)


def _jsonld_type_has_recipe(value) -> bool:
    if not value:
        return False
    if isinstance(value, str):
        return value == "Recipe" or value.endswith(":Recipe")
    if isinstance(value, list):
        return any(_jsonld_type_has_recipe(v) for v in value)
    return False


def _find_jsonld_recipe(data) -> Optional[dict]:
    if isinstance(data, list):
        for item in data:
            found = _find_jsonld_recipe(item)
            if found:
                return found
        return None

    if isinstance(data, dict):
        if _jsonld_type_has_recipe(data.get("@type")):
            return data

        graph = data.get("@graph")
        if graph is not None:
            found = _find_jsonld_recipe(graph)
            if found:
                return found

        main = data.get("mainEntity")
        if main is not None:
            found = _find_jsonld_recipe(main)
            if found:
                return found

    return None


def _extract_jsonld_recipe(soup: BeautifulSoup) -> Optional[dict]:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (script.string or "").strip()
        if not raw:
            raw = (script.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        found = _find_jsonld_recipe(data)
        if found:
            return found
    return None


def _parse_recipe_image_url(jsonld: dict) -> str:
    image = jsonld.get("image")
    if isinstance(image, list) and image:
        image0 = image[0]
        if isinstance(image0, dict) and image0.get("url"):
            return str(image0["url"])
        if isinstance(image0, str):
            return image0
    if isinstance(image, dict) and image.get("url"):
        return str(image["url"])
    if isinstance(image, str):
        return image
    return ""


def _parse_recipe_ingredients(jsonld: dict) -> list[dict]:
    out: list[dict] = []
    ingredients = jsonld.get("recipeIngredient")
    if isinstance(ingredients, list):
        for raw in ingredients:
            if not raw:
                continue
            t = _collapse_ws(str(raw))
            if not t:
                continue
            out.append({"name": t, "amount": ""})
    return out


def _parse_recipe_steps(jsonld: dict) -> list[str]:
    steps: list[str] = []

    def add(text: str):
        t = _collapse_ws(text)
        if t:
            steps.append(t)

    def walk(node):
        if not node:
            return
        if isinstance(node, str):
            # sometimes steps are in a single string separated by newlines
            for part in re.split(r"(?:\r?\n)+", node):
                add(part)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if isinstance(node, dict):
            if node.get("text"):
                add(str(node.get("text")))
            elif node.get("@type") == "HowToStep" and node.get("name"):
                add(str(node.get("name")))

            if node.get("itemListElement") is not None:
                walk(node.get("itemListElement"))
            if node.get("steps") is not None:
                walk(node.get("steps"))
            return

    walk(jsonld.get("recipeInstructions"))

    # de-dupe keep order
    out: list[str] = []
    seen = set()
    for s in steps:
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _fetch_sitemap_slugs(session: requests.Session, *, cap: int, verbose: bool = False) -> list[str]:
    """
    Best-effort: prefer sitemap because it usually contains the full URL set and
    is more stable than scraping paginated listing HTML.
    """
    prefix = f"{BASE}/myplate-kitchen/recipes/"
    seen = set()
    out: list[str] = []

    to_visit = [f"{BASE}/sitemap.xml", f"{BASE}/sitemap_index.xml"]
    visited = set()
    max_sitemaps = 20

    while to_visit and len(visited) < max_sitemaps and len(out) < cap:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            res = session.get(url, timeout=20)
            res.raise_for_status()
        except Exception as e:
            if verbose:
                print(f"[myplate_gov] sitemap fetch failed: {url}: {e}")
            continue

        try:
            root = ElementTree.fromstring(res.content)
        except Exception as e:
            if verbose:
                print(f"[myplate_gov] sitemap parse failed: {url}: {e}")
            continue

        for loc in root.findall(".//{*}loc"):
            href = (loc.text or "").strip()
            if not href:
                continue
            if href.endswith(".xml") and href.startswith(BASE) and href not in visited:
                to_visit.append(href)
                continue
            if not href.startswith(prefix):
                continue
            slug = href[len(prefix) :].split("?", 1)[0].split("#", 1)[0].strip("/")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            out.append(slug)
            if len(out) >= cap:
                break

    return out


def list_recipe_slugs(session: requests.Session, max_pages: int = 20, *, verbose: bool = False) -> list[str]:
    prefix = "/myplate-kitchen/recipes/"
    cap = max(1, int(max_pages or 0)) * 50

    sitemap_slugs = _fetch_sitemap_slugs(session, cap=cap, verbose=verbose)
    if sitemap_slugs:
        if verbose:
            print(f"[myplate_gov] sitemap slugs={len(sitemap_slugs)}")
        return sitemap_slugs

    slugs: list[str] = []
    seen = set()

    for page in range(max_pages):
        url = SEARCH_URL if page == 0 else f"{SEARCH_URL}?page={page}"
        try:
            res = session.get(url, timeout=20)
            res.raise_for_status()
        except Exception as e:
            if verbose:
                print(f"[myplate_gov] list page fetch failed: {url}: {e}")
            break
        soup = BeautifulSoup(res.text, "html.parser")

        page_slugs = []
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            href = href.split("#", 1)[0].split("?", 1)[0]
            if not href:
                continue

            if href.startswith("http://") or href.startswith("https://"):
                if not href.startswith(BASE):
                    continue
                path = href[len(BASE) :]
            else:
                path = href

            if not path.startswith(prefix):
                continue

            slug = path[len(prefix) :].strip("/")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            page_slugs.append(slug)
            slugs.append(slug)

        if verbose:
            print(f"[myplate_gov] page={page} slugs+={len(page_slugs)} total={len(slugs)}")

        if not page_slugs:
            break

    return slugs


@dataclass
class ParsedRecipe:
    slug: str
    title: str
    publish_date: str
    description: str
    cover_image_url: str
    source_url: str
    origin_url: str
    meal_types: list[str]
    categories: list[str]
    food_groups: list[str]
    prep_minutes: Optional[int]
    ingredients: list[dict]
    steps: list[str]


def fetch_recipe(session: requests.Session, slug: str) -> ParsedRecipe:
    page_url = f"{BASE}/myplate-kitchen/recipes/{slug}"
    res = session.get(page_url, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    jsonld = _extract_jsonld_recipe(soup) or {}
    title = _collapse_ws(jsonld.get("name") or slug.replace("-", " "))
    publish_date = _normalize_publish_date(str(jsonld.get("datePublished") or ""))
    description = _collapse_ws(jsonld.get("description") or "")
    cover_image_url = _parse_recipe_image_url(jsonld)

    total_time = jsonld.get("totalTime") or jsonld.get("prepTime") or ""
    prep_minutes = _parse_iso8601_duration_to_minutes(str(total_time)) if total_time else None

    ingredients = _parse_recipe_ingredients(jsonld)
    steps = _parse_recipe_steps(jsonld)

    # Best-effort tags from JSON-LD
    meal_types = _as_str_list(jsonld.get("recipeCategory"))
    categories = _as_str_list(jsonld.get("recipeCuisine"))
    categories.extend(_as_str_list(jsonld.get("keywords")))
    food_groups: list[str] = []

    origin_url = ""
    main = jsonld.get("mainEntityOfPage")
    if isinstance(main, str):
        origin_url = main
    elif isinstance(main, dict) and main.get("@id"):
        origin_url = str(main.get("@id"))
    elif jsonld.get("url"):
        origin_url = str(jsonld.get("url"))
    if origin_url == page_url:
        origin_url = ""

    return ParsedRecipe(
        slug=slug,
        title=title,
        publish_date=publish_date,
        description=description,
        cover_image_url=cover_image_url,
        source_url=page_url,
        origin_url=origin_url,
        meal_types=meal_types,
        categories=categories,
        food_groups=food_groups,
        prep_minutes=prep_minutes,
        ingredients=ingredients,
        steps=steps,
    )


def map_tags(meal_types: Iterable[str], categories: Iterable[str], food_groups: Iterable[str]) -> list[str]:
    tags: list[str] = []

    for t in meal_types:
        tags.append(MEAL_MAP.get(t, t))

    for t in categories:
        tags.append(TAG_MAP.get(t, t))

    for t in food_groups:
        tags.append(TAG_MAP.get(t, t))

    out = []
    seen = set()
    for t in tags:
        t = _collapse_ws(t)
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out
