const api = require("../../utils/api");
const storage = require("../../utils/storage");
const { STORAGE_KEYS, DEFAULT_COVER } = require("../../config");
const age = require("../../utils/age");

const app = getApp();

Page({
  data: {
    navHeight: app.globalData.navHeight,
    navCapsuleTop: app.globalData.navCapsuleTop,
    navCapsuleHeight: app.globalData.navCapsuleHeight,
    query: "",
    hasBirthday: false,
    ageText: "未设置",
    ageMonths: 0,
    activeBucket: "",
    reco: [],
    indexItems: [],
    defaultCover: DEFAULT_COVER,
    loading: true,
  },

  async onLoad() {
    this.setData({ navMarginBottom: app.globalData.navMarginBottom });
    this.refreshProfile();
    await this.loadData();
  },

  onShow() {
    if (this.getTabBar && this.getTabBar()) {
      this.getTabBar().setSelected(0);
    }
    this.refreshProfile();
  },

  refreshProfile() {
    const profile = storage.get(STORAGE_KEYS.profile, {});
    // 设置默认生日为 2024-06-24
    if (!profile.birthday) {
      profile.birthday = "2024-06-24";
      storage.set(STORAGE_KEYS.profile, profile);
    }
    const birthday = profile.birthday;
    const hasBirthday = true; // 既然有了默认值，就默认为已设置
    let ageMonths = 0;
    let ageText = "未设置";
    let activeBucket = "";

    if (hasBirthday) {
      const d = age.toDateYmd(birthday);
      ageMonths = age.diffMonths(d, new Date());
      ageText = age.formatAgeText(ageMonths);
      activeBucket = this.pickBucketByAgeMonths(ageMonths);
    }

    this.setData({ hasBirthday, ageMonths, ageText, activeBucket });
  },

  pickBucketByAgeMonths(ageMonths) {
    if (typeof ageMonths !== "number" || Number.isNaN(ageMonths)) return "";
    if (ageMonths < 0) return "";
    if (ageMonths < 6) return "4-6";
    if (ageMonths < 8) return "6-8";
    if (ageMonths < 12) return "8-12";
    if (ageMonths < 24) return "1+";
    return "2+";
  },

  async loadData() {
    // wx.showLoading({ title: "加载中" });
    this.setData({ loading: true });
    try {
      const index = await api.fetchIndex();
      const items = (index && index.items) || [];

      // Randomly shuffle items to pick recommendations
      const reco = this.shuffle(items).slice(0, 10);
      this.setData({ reco, indexItems: items });
    } finally {
      // wx.hideLoading();
      this.setData({ loading: false });
      wx.stopPullDownRefresh();
    }
  },

  shuffle(array) {
    const arr = array.slice();
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  },

  onPullDownRefresh() {
    this.refreshProfile();
    this.loadData();
  },

  onGoSearch() {
    const q = (this.data.query || "").trim();
    const url = q ? `/pages/search/index?q=${encodeURIComponent(q)}` : "/pages/search/index";
    wx.navigateTo({ url });
  },

  onRefreshReco() {
    const items = this.data.indexItems || [];
    if (items.length === 0) {
      this.loadData();
      return;
    }
    const reco = this.shuffle(items).slice(0, 10);
    this.setData({ reco });
  },

  onCoverError(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    const fallback = this.data.defaultCover;
    const reco = (this.data.reco || []).map((item) =>
      item && item.id === id ? { ...item, cover_image: fallback } : item,
    );
    this.setData({ reco });
  },

  onNavBucket(e) {
    const bucket = e.currentTarget.dataset.bucket;
    storage.set(STORAGE_KEYS.listContext, { query: "", bucket: bucket || "" });
    wx.switchTab({ url: "/pages/list/index" });
  },

  onOpenDetail(e) {
    const id = e.currentTarget.dataset.id;
    console.log("[home] open detail id =", id);
    if (!id) {
      wx.showToast({ title: "缺少食谱ID", icon: "error" });
      return;
    }
    wx.navigateTo({
      url: `/pages/detail/index?id=${encodeURIComponent(id)}`,
      fail: (err) => {
        console.error("[home] navigateTo failed:", err);
        wx.showModal({
          title: "无法打开详情页",
          content: err && err.errMsg ? err.errMsg : String(err),
          showCancel: false,
        });
      },
    });
  },

  onEditBirthday() {
    console.log("[home] open profile");
    wx.switchTab({
      url: "/pages/profile/index",
      fail: (err) => {
        console.error("[home] switchTab profile failed:", err);
        wx.showModal({
          title: "无法打开我的页面",
          content: err && err.errMsg ? err.errMsg : String(err),
          showCancel: false,
        });
      },
    });
  },
});
