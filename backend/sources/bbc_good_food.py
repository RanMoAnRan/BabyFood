"""Single-site importer for BBC Good Food recipes."""

import gzip
import json
import re
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup


BASE = "https://www.bbcgoodfood.com"

_RECIPE_PREFIX = "/recipes/"
_RE_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EXCLUDE_PREFIXES = (
    "collection/",
    "category/",
    "cuisine/",
    "diet/",
    "course/",
    "chef/",
    "author/",
    "search/",
    "tips/",
    "news/",
    "article/",
    "seasonal/",
    "occasion/",
    "user/",
    "blog/",
)

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def prepare_session(session: requests.Session) -> None:
    session.headers.update(
        {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        }
    )


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
    def parse_candidates(raw: str) -> list:
        text = (raw or "").strip()
        if not text:
            return []
        text = re.sub(r"^<!--|-->$", "", text).strip()
        text = text.replace("/*<![CDATA[*/", "").replace("/*]]>*/", "")

        try:
            return [json.loads(text)]
        except Exception:
            pass

        decoder = json.JSONDecoder()
        out = []
        idx = 0
        while idx < len(text):
            m = re.search(r"[\[{]", text[idx:])
            if not m:
                break
            idx += m.start()
            try:
                obj, end = decoder.raw_decode(text, idx)
            except json.JSONDecodeError:
                idx += 1
                continue
            out.append(obj)
            idx = end
        return out

    for script in soup.find_all("script"):
        raw = (script.string or "").strip()
        if not raw:
            raw = (script.get_text() or "").strip()
        if not raw:
            continue
        is_ld = (script.get("type") or "").lower() == "application/ld+json"
        if not is_ld and "@type" not in raw and "Recipe" not in raw:
            continue

        for data in parse_candidates(raw):
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

    out: list[str] = []
    seen = set()
    for s in steps:
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _parse_meta_content(soup: BeautifulSoup, *, name: str | None = None, prop: str | None = None) -> str:
    attrs = {}
    if name:
        attrs["name"] = name
    if prop:
        attrs["property"] = prop
    if not attrs:
        return ""
    node = soup.find("meta", attrs=attrs)
    if not node:
        return ""
    return _collapse_ws(node.get("content") or "")


def _extract_text_list(nodes: list) -> list[str]:
    out: list[str] = []
    for node in nodes or []:
        text = _collapse_ws(node.get_text(" "))
        if text:
            out.append(text)
    seen = set()
    deduped = []
    for t in out:
        if t in seen:
            continue
        seen.add(t)
        deduped.append(t)
    return deduped


def _parse_html_recipe(soup: BeautifulSoup) -> Optional[dict]:
    title_el = soup.select_one("[itemprop='name']") or soup.select_one("h1")
    title = _collapse_ws(title_el.get_text(" ")) if title_el else ""
    if not title:
        return None

    desc_el = soup.select_one("[itemprop='description']")
    description = _collapse_ws(desc_el.get_text(" ")) if desc_el else ""
    if not description:
        description = _parse_meta_content(soup, name="description")

    cover_image_url = _parse_meta_content(soup, prop="og:image")
    if not cover_image_url:
        cover_image_url = _parse_meta_content(soup, name="og:image")

    ingredients_nodes = soup.select("[itemprop='recipeIngredient']")
    ingredients = _extract_text_list(ingredients_nodes)
    if not ingredients:
        ingredients = _extract_text_list(
            soup.select("li.ingredients-list__item")
            or soup.select("li.recipe__ingredient")
            or soup.select(".ingredients__list li")
        )

    steps: list[str] = []
    instr_nodes = soup.select("[itemprop='recipeInstructions']")
    if instr_nodes:
        for node in instr_nodes:
            li_nodes = node.find_all("li")
            if li_nodes:
                steps.extend(_extract_text_list(li_nodes))
            else:
                t = _collapse_ws(node.get_text(" "))
                if t:
                    steps.append(t)
    if not steps:
        steps = _extract_text_list(
            soup.select("li.method__item")
            or soup.select(".method__list li")
            or soup.select(".recipe-method__list li")
        )

    if not ingredients and not steps:
        return None

    publish_date = _normalize_publish_date(_parse_meta_content(soup, prop="article:published_time"))

    return {
        "title": title,
        "description": description,
        "cover_image_url": cover_image_url,
        "publish_date": publish_date,
        "ingredients": ingredients,
        "steps": steps,
    }


def _fetch_sitemap_xml(session: requests.Session, url: str, *, verbose: bool = False):
    try:
        res = session.get(url, timeout=20)
        res.raise_for_status()
    except Exception as e:
        if verbose:
            print(f"[bbc_good_food] sitemap fetch failed: {url}: {e}")
        return None
    content = res.content
    if url.endswith(".gz"):
        try:
            content = gzip.decompress(content)
        except Exception as e:
            if verbose:
                print(f"[bbc_good_food] sitemap gzip failed: {url}: {e}")
            return None
    try:
        return ElementTree.fromstring(content)
    except Exception as e:
        if verbose:
            print(f"[bbc_good_food] sitemap parse failed: {url}: {e}")
        return None


def _is_recipe_path(path: str) -> bool:
    if not path.startswith(_RECIPE_PREFIX):
        return False
    rest = path[len(_RECIPE_PREFIX) :].lstrip("/")
    if not rest:
        return False
    for prefix in _EXCLUDE_PREFIXES:
        if rest.startswith(prefix):
            return False
    return True


def _fetch_sitemap_slugs(session: requests.Session, *, cap: int, verbose: bool = False) -> list[str]:
    seen = set()
    out: list[str] = []

    to_visit = [f"{BASE}/sitemap.xml", f"{BASE}/sitemap_index.xml"]
    visited = set()
    max_sitemaps = 30

    while to_visit and len(visited) < max_sitemaps and len(out) < cap:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        root = _fetch_sitemap_xml(session, url, verbose=verbose)
        if root is None:
            continue

        for loc in root.findall(".//{*}loc"):
            href = (loc.text or "").strip()
            if not href:
                continue
            if (href.endswith(".xml") or href.endswith(".xml.gz")) and href.startswith(BASE):
                if href not in visited:
                    to_visit.append(href)
                continue

            path = urlparse(href).path
            if not _is_recipe_path(path):
                continue
            slug = path[len(_RECIPE_PREFIX) :].strip("/")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            out.append(slug)
            if len(out) >= cap:
                break

    return out


def list_recipe_slugs(session: requests.Session, max_pages: int = 20, *, verbose: bool = False) -> list[str]:
    cap = max(1, int(max_pages or 0)) * 50
    slugs = _fetch_sitemap_slugs(session, cap=cap, verbose=verbose)
    if verbose:
        print(f"[bbc_good_food] sitemap slugs={len(slugs)}")
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
    if slug.startswith("http://") or slug.startswith("https://"):
        page_url = slug
    else:
        page_url = f"{BASE}/recipes/{slug.strip('/')}/"

    res = session.get(page_url, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    jsonld = _extract_jsonld_recipe(soup) or {}
    if jsonld:
        title = _collapse_ws(jsonld.get("name") or slug.replace("-", " "))
        publish_date = _normalize_publish_date(str(jsonld.get("datePublished") or ""))
        description = _collapse_ws(jsonld.get("description") or "")
        cover_image_url = _parse_recipe_image_url(jsonld)

        total_time = jsonld.get("totalTime") or jsonld.get("prepTime") or jsonld.get("cookTime") or ""
        prep_minutes = _parse_iso8601_duration_to_minutes(str(total_time)) if total_time else None

        ingredients = _parse_recipe_ingredients(jsonld)
        steps = _parse_recipe_steps(jsonld)

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
    else:
        parsed = _parse_html_recipe(soup)
        if not parsed:
            raise ValueError("jsonld recipe not found")

        title = parsed["title"]
        description = parsed["description"]
        cover_image_url = parsed["cover_image_url"]
        publish_date = parsed["publish_date"] or ""
        prep_minutes = None
        ingredients = [{"name": t, "amount": ""} for t in parsed["ingredients"]]
        steps = parsed["steps"]
        meal_types = []
        categories = []
        food_groups = []
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
        tags.append(t)
    for t in categories:
        tags.append(t)
    for t in food_groups:
        tags.append(t)

    out = []
    seen = set()
    for t in tags:
        t = _collapse_ws(t)
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out
