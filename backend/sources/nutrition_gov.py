"""Single-site importer for Nutrition.gov recipes."""

import json
import re
from dataclasses import dataclass
from typing import Iterable, Optional

import requests
from bs4 import BeautifulSoup


BASE = "https://www.nutrition.gov"
SEARCH_URL = f"{BASE}/recipes/search"


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
}


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _parse_minutes(text: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*minutes?", text or "", flags=re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1))


def _extract_jsonld_recipe(soup: BeautifulSoup) -> Optional[dict]:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (script.string or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("@type") == "Recipe":
            return data
    return None


def list_recipe_slugs(session: requests.Session, max_pages: int = 20) -> list[str]:
    slugs: list[str] = []
    seen = set()
    for page in range(max_pages):
        url = f"{SEARCH_URL}?page={page}"
        res = session.get(url, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        cards = soup.select("div.recipe[about^='/recipes/']")
        page_slugs = []
        for card in cards:
            about = card.get("about") or ""
            if not about.startswith("/recipes/"):
                continue
            slug = about[len("/recipes/") :]
            if not slug or slug in seen:
                continue
            seen.add(slug)
            page_slugs.append(slug)
            slugs.append(slug)

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
    page_url = f"{BASE}/recipes/{slug}"
    res = session.get(page_url, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    jsonld = _extract_jsonld_recipe(soup) or {}
    title = _collapse_ws(jsonld.get("name") or slug.replace("-", " "))
    publish_date = _collapse_ws(jsonld.get("datePublished") or "")
    description = _collapse_ws(jsonld.get("description") or "")

    cover_image_url = ""
    image = jsonld.get("image")
    if isinstance(image, list) and image:
        image0 = image[0]
        if isinstance(image0, dict) and image0.get("url"):
            cover_image_url = str(image0["url"])
        elif isinstance(image0, str):
            cover_image_url = image0
    elif isinstance(image, dict) and image.get("url"):
        cover_image_url = str(image["url"])
    elif isinstance(image, str):
        cover_image_url = image

    origin_url = ""
    creator = jsonld.get("creator")
    if isinstance(creator, dict) and creator.get("url"):
        origin_url = str(creator["url"])

    # Meal type
    meal_types = []
    for el in soup.select("div.field--name-recipe-course span.field--item"):
        t = _collapse_ws(el.get_text(" "))
        if t:
            meal_types.append(t)

    # Category
    categories = []
    for el in soup.select("div.field--name-recipe-category a"):
        t = _collapse_ws(el.get_text(" "))
        if t:
            categories.append(t)

    # Food group
    food_groups = []
    for el in soup.select("div.field--name-recipe-food-group span.field--item"):
        t = _collapse_ws(el.get_text(" "))
        if t:
            food_groups.append(t)

    prep_minutes = None
    prep_el = soup.select_one("div.field--name-recipe-prep-time .field--item")
    if prep_el:
        prep_minutes = _parse_minutes(prep_el.get_text(" "))

    ingredients = []
    for row in soup.select("div.field--name-ingredients .field--name-ingredients .field--item"):
        qty_el = row.select_one(".quantity-unit")
        name_el = row.select_one(".ingredient-name")
        if not name_el:
            continue
        amount = _collapse_ws(qty_el.get_text(" ")) if qty_el else ""
        name = _collapse_ws(name_el.get_text(" "))
        if not name:
            continue
        ingredients.append({"name": name, "amount": amount})

    steps = []
    for li in soup.select("div.field--name-recipe-instructions ol li"):
        t = _collapse_ws(li.get_text(" "))
        if t:
            steps.append(t)

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

    # de-dupe keep order
    out = []
    seen = set()
    for t in tags:
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out
