const api = require("../../utils/api");
const age = require("../../utils/age");
const favorites = require("../../utils/favorites");
const storage = require("../../utils/storage");
const { STORAGE_KEYS } = require("../../config");

function formatDateShort(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function formatStageText(bucket) {
  if (!bucket) return "";
  if (bucket === "4-6") return "4-6个月";
  if (bucket === "6-8") return "6-8个月";
  if (bucket === "8-12") return "8-12个月";
  if (bucket === "1+") return "1岁+";
  if (bucket === "2+") return "2岁+";
  return "";
}

const app = getApp();

Page({
  data: {
    navHeight: app.globalData.navHeight,
    navCapsuleTop: app.globalData.navCapsuleTop,
    navCapsuleHeight: app.globalData.navCapsuleHeight,
    birthday: "",
    ageText: "",
    ageStageText: "",
    allergenInput: "",
    allergenList: [],
    favCount: 0,
    recipeCount: "",
  },

  async onLoad() {
    this.setData({ navMarginBottom: app.globalData.navMarginBottom });
    this.loadProfile();
    this.loadStats();
  },

  onShow() {
    if (this.getTabBar && this.getTabBar()) {
      this.getTabBar().setSelected(3);
    }
    this.loadProfile();
    this.loadStats();
  },

  getAgeInfo(birthday) {
    const birthDate = age.toDateYmd(birthday);
    if (!birthDate) return { ageText: "", ageStageText: "" };
    const months = age.diffMonths(birthDate, new Date());
    return {
      ageText: age.formatAgeText(months),
      ageStageText: formatStageText(age.bucketByMonths(months)),
    };
  },

  loadProfile() {
    const profile = storage.get(STORAGE_KEYS.profile, {});
    const birthday = profile && profile.birthday ? String(profile.birthday) : "";
    const rawAllergens = profile && profile.allergens ? String(profile.allergens) : "";
    const allergenList = rawAllergens.split(/[,，、\s]+/).filter(Boolean);
    const { ageText, ageStageText } = this.getAgeInfo(birthday);
    this.setData({ birthday, allergenList, ageText, ageStageText });
  },

  loadStats() {
    const favIds = favorites.getFavorites();
    const manifest = storage.get(STORAGE_KEYS.manifest, null) || {};
    const favCount = Array.isArray(favIds) ? favIds.length : 0;
    const recipeCount = manifest && Number.isFinite(manifest.recipe_count) ? String(manifest.recipe_count) : "";
    this.setData({
      favCount,
      recipeCount,
    });
  },

  onBirthdayChange(e) {
    const birthday = e.detail && e.detail.value ? e.detail.value : "";
    const profile = storage.get(STORAGE_KEYS.profile, {});
    profile.birthday = birthday;
    storage.set(STORAGE_KEYS.profile, profile);
    const { ageText, ageStageText } = this.getAgeInfo(birthday);
    this.setData({ birthday, ageText, ageStageText });
    wx.showToast({ title: "已保存", icon: "success" });
  },

  onAllergenInput(e) {
    this.setData({ allergenInput: e.detail.value });
  },

  onAddAllergen() {
    const val = (this.data.allergenInput || "").trim();
    if (!val) return;
    const list = this.data.allergenList || [];
    if (list.includes(val)) {
      wx.showToast({ title: "已存在", icon: "none" });
      return;
    }
    const newList = [...list, val];
    this.updateAllergens(newList);
    this.setData({ allergenInput: "" });
  },

  onRemoveAllergen(e) {
    const idx = e.currentTarget.dataset.index;
    const list = this.data.allergenList || [];
    const newList = list.filter((_, i) => i !== idx);
    this.updateAllergens(newList);
  },

  updateAllergens(list) {
    const profile = storage.get(STORAGE_KEYS.profile, {});
    profile.allergens = list.join(",");
    storage.set(STORAGE_KEYS.profile, profile);
    this.setData({ allergenList: list });
  },

  onGoFavorites() {
    wx.switchTab({ url: "/pages/favorites/index" });
  },

  onGoSearch() {
    wx.navigateTo({ url: "/pages/search/index" });
  },

  onClearDataCache() {
    const ok1 = storage.remove(STORAGE_KEYS.manifest);
    const ok2 = storage.remove(STORAGE_KEYS.index);
    const ok3 = storage.remove(STORAGE_KEYS.cdnBase);
    const ok4 = storage.clearByPrefix(STORAGE_KEYS.cachePrefix, [STORAGE_KEYS.profile, STORAGE_KEYS.favorites]);
    const ok = ok1 && ok2 && ok3 && ok4;
    wx.showToast({ title: ok ? "已清理" : "清理失败", icon: ok ? "success" : "error" });
    this.loadStats();
  },

  async onCheckUpdate() {
    wx.showLoading({ title: "检查中" });
    try {
      const { updated } = await api.checkUpdate();
      if (updated) {
        await api.fetchIndex({ force: true });
        wx.showToast({ title: "已更新", icon: "success" });
      } else {
        wx.showToast({ title: "已是最新", icon: "success" });
      }
    } finally {
      wx.hideLoading();
    }
    this.loadStats();
  },

  onShareAppMessage() {
    return {
      title: "宝宝辅食 - 科学喂养每一餐",
      path: "/pages/home/index",
    };
  },
});
