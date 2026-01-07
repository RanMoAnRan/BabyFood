const api = require("../../utils/api");
const storage = require("../../utils/storage");
const { STORAGE_KEYS } = require("../../config");
const age = require("../../utils/age");

Page({
  data: {
    query: "",
    hasBirthday: false,
    ageText: "未设置",
    ageMonths: 0,
    activeBucket: "",
    reco: [],
  },

  async onLoad() {
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
    const birthday = profile && profile.birthday ? String(profile.birthday) : "";
    const hasBirthday = Boolean(birthday);
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
    wx.showLoading({ title: "加载中" });
    try {
      const [manifest, index] = await Promise.all([api.fetchManifest(), api.fetchIndex()]);
      const latestIds = (manifest && manifest.latest_ids) || [];
      const items = (index && index.items) || [];

      const map = new Map(items.map((x) => [x.id, x]));
      let reco = latestIds.map((id) => map.get(id)).filter(Boolean).slice(0, 10);
      if (reco.length === 0 && items.length > 0) {
        // 容灾：manifest/index 不一致或网络降级时，至少展示列表前 N 条
        reco = items.slice(0, 10);
      }
      this.setData({ reco });
    } finally {
      wx.hideLoading();
    }
  },

  onQueryInput(e) {
    this.setData({ query: (e.detail && e.detail.value) || "" });
  },

  onSearch() {
    const q = (this.data.query || "").trim();
    wx.navigateTo({ url: `/pages/list/index?q=${encodeURIComponent(q)}` });
  },

  onNavBucket(e) {
    const bucket = e.currentTarget.dataset.bucket;
    wx.navigateTo({ url: `/pages/list/index?bucket=${encodeURIComponent(bucket)}` });
  },

  onOpenAll() {
    wx.navigateTo({ url: "/pages/list/index" });
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
