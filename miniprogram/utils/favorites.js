const { STORAGE_KEYS } = require("../config");
const storage = require("./storage");

function getFavorites() {
  const ids = storage.get(STORAGE_KEYS.favorites, []);
  return Array.isArray(ids) ? ids : [];
}

function isFavorite(id) {
  return getFavorites().includes(id);
}

function toggleFavorite(id) {
  if (!id) return { ids: getFavorites(), isFavorite: false };
  const ids = getFavorites();
  const idx = ids.indexOf(id);
  if (idx >= 0) ids.splice(idx, 1);
  else ids.unshift(id);
  storage.set(STORAGE_KEYS.favorites, ids);
  return { ids, isFavorite: ids.includes(id) };
}

function removeFavorite(id) {
  const ids = getFavorites().filter((x) => x !== id);
  storage.set(STORAGE_KEYS.favorites, ids);
  return ids;
}

function removeFavorites(ids) {
  const removeSet = new Set(Array.isArray(ids) ? ids : []);
  if (removeSet.size === 0) return getFavorites();
  const next = getFavorites().filter((x) => !removeSet.has(x));
  storage.set(STORAGE_KEYS.favorites, next);
  return next;
}

module.exports = { getFavorites, isFavorite, toggleFavorite, removeFavorite, removeFavorites };
