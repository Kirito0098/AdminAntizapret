(function () {
  function fmtRate(val) {
    const v = Number(val) || 0;
    return v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2);
  }

  function fmtVolume(val, unit) {
    const v = Number(val) || 0;
    const units = unit === "MB" ? ["МБ", "ГБ", "ТБ", "ПБ"] : ["Мбит", "Гбит", "Тбит", "Пбит"];
    let i = 0;
    let x = v;
    while (x >= 1024 && i < units.length - 1) {
      x /= 1024;
      i += 1;
    }
    return `${x.toFixed(x >= 100 ? 0 : x >= 10 ? 1 : 2)} ${units[i]}`;
  }

  function fmtVolumeFromBytes(bytes, unit) {
    const mb = (Number(bytes) || 0) / (1024 * 1024);
    return fmtVolume(unit === "MB" ? mb : mb * 8, unit);
  }

  window.ServerMonitorFmt = {
    fmtRate,
    fmtVolume,
    fmtVolumeFromBytes,
  };
})();
