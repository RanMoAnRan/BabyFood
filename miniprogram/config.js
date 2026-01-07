const LOCAL_CDN_BASE = "http://127.0.0.1:8000/backend/data";
const REMOTE_CDN_BASE = "https://cdn.jsdelivr.net/gh/RanMoAnRan/BabyFood@main/backend/data";

function getCdnBase() {
  // develop/trial/release
  // - develop：默认走本地联调（你已运行 `python3 -m http.server 8000`）
  //   浏览器可访问：http://127.0.0.1:8000/backend/data/manifest.json
  // - trial/release：走线上 CDN
  //
  // 备注：如需固定版本，建议将 REMOTE_CDN_BASE 改为：
  // https://cdn.jsdelivr.net/gh/<owner>/<repo>@<tag_or_commit_sha>/backend/data
  try {
    if (typeof wx !== "undefined" && wx.getAccountInfoSync) {
      const info = wx.getAccountInfoSync();
      const env = info && info.miniProgram && info.miniProgram.envVersion;
      if (env === "develop") return LOCAL_CDN_BASE;
    }
  } catch (e) {
    // ignore
  }
  return REMOTE_CDN_BASE;
}

module.exports = {
  CDN_BASE: getCdnBase(),
  LOCAL_CDN_BASE,
  REMOTE_CDN_BASE,
  getCdnBase,

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
