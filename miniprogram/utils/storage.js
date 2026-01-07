function get(key, defaultValue = null) {
  try {
    const value = wx.getStorageSync(key);
    return value === "" || value === undefined ? defaultValue : value;
  } catch (e) {
    return defaultValue;
  }
}

function set(key, value) {
  try {
    wx.setStorageSync(key, value);
    return true;
  } catch (e) {
    return false;
  }
}

function remove(key) {
  try {
    wx.removeStorageSync(key);
    return true;
  } catch (e) {
    return false;
  }
}

function clearByPrefix(prefix, keepKeys = []) {
  const keepSet = new Set(keepKeys);
  try {
    const info = wx.getStorageInfoSync();
    (info.keys || []).forEach((k) => {
      if (keepSet.has(k)) return;
      if (k.startsWith(prefix)) wx.removeStorageSync(k);
    });
    return true;
  } catch (e) {
    return false;
  }
}

module.exports = { get, set, remove, clearByPrefix };

