function toDateYmd(ymd) {
  if (!ymd) return null;
  const parts = String(ymd).split("-");
  if (parts.length !== 3) return null;
  const year = Number(parts[0]);
  const month = Number(parts[1]) - 1;
  const day = Number(parts[2]);
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null;
  return new Date(year, month, day);
}

function diffMonths(fromDate, toDate) {
  if (!(fromDate instanceof Date) || !(toDate instanceof Date)) return 0;
  let months = (toDate.getFullYear() - fromDate.getFullYear()) * 12 + (toDate.getMonth() - fromDate.getMonth());
  if (toDate.getDate() < fromDate.getDate()) months -= 1;
  return Math.max(0, months);
}

function formatAgeText(months) {
  const years = Math.floor(months / 12);
  const remain = months % 12;
  if (years <= 0) return `${remain}个月`;
  if (remain === 0) return `${years}岁`;
  return `${years}岁${remain}个月`;
}

function bucketByMonths(months) {
  if (months < 6) return "4-6";
  if (months < 8) return "6-8";
  if (months < 12) return "8-12";
  if (months < 24) return "1+";
  return "2+";
}

module.exports = { toDateYmd, diffMonths, formatAgeText, bucketByMonths };

