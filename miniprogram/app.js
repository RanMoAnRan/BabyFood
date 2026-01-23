App({
  globalData: {
    navHeight: 0,
    statusBarHeight: 0,
    navCapsuleTop: 0,
    navCapsuleHeight: 0,
    menuButtonInfo: {},
  },
  onLaunch() {
    const systemInfo = wx.getSystemInfoSync();
    const menu = wx.getMenuButtonBoundingClientRect();
    
    // 导航栏总高度
    const navHeight = menu.top + menu.bottom - systemInfo.statusBarHeight;
    
    this.globalData.statusBarHeight = systemInfo.statusBarHeight;
    this.globalData.menuButtonInfo = menu;
    this.globalData.navHeight = navHeight;
    
    // 胶囊位置信息，用于直接对齐
    this.globalData.navCapsuleTop = menu.top;
    this.globalData.navCapsuleHeight = menu.height;
  }
});