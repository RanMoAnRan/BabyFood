function requestJson(url, timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    wx.request({
      url,
      method: "GET",
      dataType: "json",
      timeout: timeoutMs,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
          return;
        }
        reject(new Error(`HTTP ${res.statusCode}`));
      },
      fail: (err) => reject(err),
    });
  });
}

module.exports = { requestJson };

