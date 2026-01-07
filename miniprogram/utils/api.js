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

  const url = withQuery(joinUrl(CDN_BASE, PATHS.manifest), force ? { t: Date.now() } : {});
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
  if (!force && cached && Array.isArray(cached.items)) return cached;

  let manifest = storage.get(STORAGE_KEYS.manifest, null);
  if (!manifest || !manifest.version) manifest = await fetchManifest();
  const bust = manifest && manifest.version ? manifest.version : "";
  const url = withQuery(joinUrl(CDN_BASE, PATHS.index), force ? { v: bust, t: Date.now() } : { v: bust });
  try {
    const data = await request.requestJson(url);
    if (data && Array.isArray(data.items)) {
      data.items = data.items.map((it) => ({ ...it, cover_image: normalizeMediaUrl(it.cover_image) }));
      storage.set(STORAGE_KEYS.index, data);
    }
    return data;
  } catch (e) {
    if (cached && Array.isArray(cached.items)) return cached;
    return loadSeedJson(PATHS.index);
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
  if (!force && cached && cached.id) return cached;

  let manifest = storage.get(STORAGE_KEYS.manifest, null);
  if (!manifest || !manifest.version) manifest = await fetchManifest();
  const bust = manifest && manifest.version ? manifest.version : "";
  const url = withQuery(joinUrl(CDN_BASE, `${PATHS.recipeDir}/${id}.json`), force ? { v: bust, t: Date.now() } : { v: bust });
  try {
    const data = await request.requestJson(url);
    if (data && data.id) {
      data.cover_image = normalizeMediaUrl(data.cover_image);
      if (Array.isArray(data.steps)) {
        data.steps = data.steps.map((s) => ({ ...s, img: normalizeMediaUrl(s.img) }));
      }
      storage.set(key, data);
    }
    return data;
  } catch (e) {
    if (cached && cached.id) return cached;
    return loadSeedJson(`${PATHS.recipeDir}/${id}.json`);
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
