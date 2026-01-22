const api = require("../../utils/api");
const storage = require("../../utils/storage");
const { STORAGE_KEYS } = require("../../config");

Page({
  data: {
    birthday: "",
  },

  async onLoad() {
    this.loadProfile();
  },

  onShow() {
    if (this.getTabBar && this.getTabBar()) {
      this.getTabBar().setSelected(3);
    }
    this.loadProfile();
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

  onClearDataCache() {
    const ok1 = storage.remove(STORAGE_KEYS.manifest);
    const ok2 = storage.remove(STORAGE_KEYS.index);
    const ok3 = storage.remove(STORAGE_KEYS.cdnBase);
    const ok4 = storage.clearByPrefix(STORAGE_KEYS.cachePrefix, [STORAGE_KEYS.profile, STORAGE_KEYS.favorites]);
    const ok = ok1 && ok2 && ok3 && ok4;
    wx.showToast({ title: ok ? "已清理" : "清理失败", icon: ok ? "success" : "error" });
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
  },
});
