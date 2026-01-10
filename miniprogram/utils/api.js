const { CDN_BASE, PATHS, STORAGE_KEYS } = require("../config");
const request = require("./request");
const storage = require("./storage");

function joinUrl(base, path) {
  if (!base.endsWith("/")) base += "/";
  return base + path.replace(/^\//, "");
}

function withQuery(url, params) {
  const q = Object.entries(params || {})
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  if (!q) return url;
  return url.includes("?") ? `${url}&${q}` : `${url}?${q}`;
}

function normalizeMediaUrl(maybeUrl) {
  if (!maybeUrl) return maybeUrl;
  if (/^https?:\/\//i.test(maybeUrl)) return maybeUrl;
  return joinUrl(CDN_BASE, maybeUrl);
}

function normalizeMealTags(tags) {
  if (!Array.isArray(tags)) return tags;
  const out = [];
  const seen = new Set();
  let changed = false;

  const add = (t) => {
    const key = String(t || "");
    if (!key) return;
    if (seen.has(key)) {
      changed = true;
      return;
    }
    seen.add(key);
    out.push(key);
  };

  tags.forEach((t) => {
    if (!t) return;
    const s = String(t);

    // Backward-compat for existing dataset tags
    if (s === "点心") {
      changed = true;
      add("小吃");
      return;
    }
    if (s === "正餐") {
      changed = true;
      // Legacy dataset does not distinguish lunch vs dinner.
      // Keep "正餐" so the UI can present a single "正餐" filter to avoid duplicated lists.
      add("正餐");
      return;
    }

    // Optional compat if upstream ever returns English meal tags
    if (s === "Breakfast") {
      changed = true;
      add("早餐");
      return;
    }
    if (s === "Lunch") {
      changed = true;
      add("午餐");
      return;
    }
    if (s === "Dinner") {
      changed = true;
      add("晚餐");
      return;
    }
    if (s === "Snack") {
      changed = true;
      add("小吃");
      return;
    }

    add(s);
  });

  if (!changed && out.length === tags.length) return tags;
  return out;
}

function normalizeIndexData(data) {
  if (!data || !Array.isArray(data.items)) return data;
  let changed = false;
  const items = data.items.map((it) => {
    if (!it) return it;
    const nextCover = normalizeMediaUrl(it.cover_image);
    const nextTags = normalizeMealTags(it.tags);
    if (nextCover === it.cover_image && nextTags === it.tags) return it;
    changed = true;
    return { ...it, cover_image: nextCover, tags: nextTags };
  });
  if (!changed) return data;
  return { ...data, items };
}

function normalizeRecipeData(data) {
  if (!data || !data.id) return data;
  let changed = false;
  const out = { ...data };

  const nextCover = normalizeMediaUrl(data.cover_image);
  if (nextCover !== data.cover_image) {
    out.cover_image = nextCover;
    changed = true;
  }

  const nextTags = normalizeMealTags(data.tags);
  if (nextTags !== data.tags) {
    out.tags = nextTags;
    changed = true;
  }

  if (Array.isArray(data.steps)) {
    let stepsChanged = false;
    const steps = data.steps.map((s) => {
      if (!s) return s;
      const nextImg = normalizeMediaUrl(s.img);
      if (nextImg === s.img) return s;
      stepsChanged = true;
      return { ...s, img: nextImg };
    });
    if (stepsChanged) {
      out.steps = steps;
      changed = true;
    }
  }

  return changed ? out : data;
}

function loadSeedJson(relPath) {
  try {
    return require(`../seed/${relPath}`);
  } catch (e) {
    return null;
  }
}

async function fetchManifest({ force = false } = {}) {
  const cached = storage.get(STORAGE_KEYS.manifest, null);
  if (!force && cached && cached.version) return cached;

  const needBust = force || !cached || !cached.version;
  const url = withQuery(joinUrl(CDN_BASE, PATHS.manifest), needBust ? { t: Date.now() } : {});
  try {
    const data = await request.requestJson(url);
    if (data && data.version) storage.set(STORAGE_KEYS.manifest, data);
    return data;
  } catch (e) {
    if (cached && cached.version) return cached;
    return loadSeedJson(PATHS.manifest);
  }
}

async function fetchIndex({ force = false } = {}) {
  const cached = storage.get(STORAGE_KEYS.index, null);
  if (!force && cached && Array.isArray(cached.items)) {
    const normalized = normalizeIndexData(cached);
    if (normalized !== cached) storage.set(STORAGE_KEYS.index, normalized);
    return normalized;
  }

  let manifest = storage.get(STORAGE_KEYS.manifest, null);
  if (!manifest || !manifest.version) manifest = await fetchManifest();
  const bust = manifest && manifest.version ? manifest.version : "";
  const url = withQuery(joinUrl(CDN_BASE, PATHS.index), force ? { v: bust, t: Date.now() } : { v: bust });
  try {
    const data = await request.requestJson(url);
    const normalized = normalizeIndexData(data);
    if (normalized && Array.isArray(normalized.items)) storage.set(STORAGE_KEYS.index, normalized);
    return normalized;
  } catch (e) {
    if (cached && Array.isArray(cached.items)) {
      const normalized = normalizeIndexData(cached);
      if (normalized !== cached) storage.set(STORAGE_KEYS.index, normalized);
      return normalized;
    }
    return normalizeIndexData(loadSeedJson(PATHS.index));
  }
}

function recipeCacheKey(id, version) {
  const v = version ? String(version) : "0";
  return `${STORAGE_KEYS.cachePrefix}recipe_${id}_v${v}`;
}

async function fetchRecipe(id, { force = false, version = null } = {}) {
  if (!id) return null;
  const key = recipeCacheKey(id, version);
  const cached = storage.get(key, null);
  if (!force && cached && cached.id) {
    const normalized = normalizeRecipeData(cached);
    if (normalized !== cached) storage.set(key, normalized);
    return normalized;
  }

  let manifest = storage.get(STORAGE_KEYS.manifest, null);
  if (!manifest || !manifest.version) manifest = await fetchManifest();
  const bust = manifest && manifest.version ? manifest.version : "";
  const url = withQuery(joinUrl(CDN_BASE, `${PATHS.recipeDir}/${id}.json`), force ? { v: bust, t: Date.now() } : { v: bust });
  try {
    const data = await request.requestJson(url);
    const normalized = normalizeRecipeData(data);
    if (normalized && normalized.id) storage.set(key, normalized);
    return normalized;
  } catch (e) {
    if (cached && cached.id) {
      const normalized = normalizeRecipeData(cached);
      if (normalized !== cached) storage.set(key, normalized);
      return normalized;
    }
    return normalizeRecipeData(loadSeedJson(`${PATHS.recipeDir}/${id}.json`));
  }
}

async function checkUpdate() {
  const oldManifest = storage.get(STORAGE_KEYS.manifest, null);
  const newManifest = await fetchManifest({ force: true });
  const updated = Boolean(
    newManifest &&
      newManifest.version &&
      (!oldManifest || String(oldManifest.version) !== String(newManifest.version))
  );
  return { updated, manifest: newManifest };
}

module.exports = { fetchManifest, fetchIndex, fetchRecipe, checkUpdate };
