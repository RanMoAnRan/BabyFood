const api = require("../../utils/api");
const storage = require("../../utils/storage");
const favorites = require("../../utils/favorites");
const { STORAGE_KEYS } = require("../../config");

Page({
  data: {
    birthday: "",
    favItems: [],
  },

  async onLoad() {
    this.loadProfile();
    await this.loadFavorites();
  },

  onShow() {
    if (this.getTabBar && this.getTabBar()) {
      this.getTabBar().setSelected(1);
    }
    this.loadProfile();
    this.loadFavorites();
  },

  loadProfile() {
    const profile = storage.get(STORAGE_KEYS.profile, {});
    const birthday = profile && profile.birthday ? String(profile.birthday) : "";
    this.setData({ birthday });
  },

  onBirthdayChange(e) {
    const birthday = e.detail && e.detail.value ? e.detail.value : "";
    const profile = storage.get(STORAGE_KEYS.profile, {});
    profile.birthday = birthday;
    storage.set(STORAGE_KEYS.profile, profile);
    this.setData({ birthday });
    wx.showToast({ title: "已保存", icon: "success" });
  },

  async loadFavorites() {
    const ids = favorites.getFavorites();
    if (ids.length === 0) {
      this.setData({ favItems: [] });
      return;
    }
    const index = await api.fetchIndex();
    const items = (index && index.items) || [];
    const map = new Map(items.map((x) => [x.id, x]));
    const favItems = ids.map((id) => map.get(id)).filter(Boolean);
    this.setData({ favItems });
  },

  onOpenDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/detail/index?id=${encodeURIComponent(id)}` });
  },

  onRemoveFav(e) {
    const id = e.currentTarget.dataset.id;
    favorites.removeFavorite(id);
    this.loadFavorites();
  },

  onClearDataCache() {
    const ok1 = storage.remove(STORAGE_KEYS.manifest);
    const ok2 = storage.remove(STORAGE_KEYS.index);
    const ok3 = storage.clearByPrefix(STORAGE_KEYS.cachePrefix, [STORAGE_KEYS.profile, STORAGE_KEYS.favorites]);
    const ok = ok1 && ok2 && ok3;
    wx.showToast({ title: ok ? "已清理" : "清理失败", icon: ok ? "success" : "error" });
  },

  async onCheckUpdate() {
    wx.showLoading({ title: "检查中" });
    try {
      const { updated } = await api.checkUpdate();
      if (updated) {
        await api.fetchIndex({ force: true });
        wx.showToast({ title: "已更新", icon: "success" });
        await this.loadFavorites();
      } else {
        wx.showToast({ title: "已是最新", icon: "success" });
      }
    } finally {
      wx.hideLoading();
    }
  },
});
