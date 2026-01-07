module.exports = {
  // 本地联调（方案A）：你已运行 `python3 -m http.server 8000`
  // 浏览器可访问：http://127.0.0.1:8000/backend/data/manifest.json
  CDN_BASE: "http://127.0.0.1:8000/backend/data",

  // 上线/远程（方案B）：改成你的仓库 jsDelivr 前缀，如：
  // https://cdn.jsdelivr.net/gh/<owner>/<repo>@<commit_sha>/backend/data
  // 建议走 version 化 URL（@<commit_sha> 或 @<tag>），不要直接 latest，避免 CDN 缓存不一致。
  // CDN_BASE: "https://cdn.jsdelivr.net/gh/OWNER/REPO@VERSION/backend/data",

  PATHS: {
    manifest: "manifest.json",
    index: "recipes_index.json",
    recipeDir: "recipes",
  },

  STORAGE_KEYS: {
    manifest: "bf_manifest",
    index: "bf_index",
    favorites: "bf_favorites",
    profile: "bf_profile",
    cachePrefix: "bf_cache_",
  },
};
