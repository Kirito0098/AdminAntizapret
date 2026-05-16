(function () {
  function parseProtocolTokens(rawValue) {
    return String(rawValue || "")
      .toLowerCase()
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function protocolMatches(rawValue, selectedProtocol) {
    const selected = String(selectedProtocol || "all").toLowerCase();
    if (selected === "all") {
      return true;
    }
    return parseProtocolTokens(rawValue).includes(selected);
  }

  function parseServerDateTime(rawValue) {
    const raw = String(rawValue || "").trim();
    if (!raw || raw === "-") {
      return null;
    }
    const utcLike = raw.replace(" ", "T") + "Z";
    const utcDate = new Date(utcLike);
    if (!Number.isNaN(utcDate.getTime())) {
      return utcDate;
    }
    const localLike = raw.replace(" ", "T");
    const localDate = new Date(localLike);
    if (!Number.isNaN(localDate.getTime())) {
      return localDate;
    }
    return null;
  }

  const trafficLabelFormatters = {
    minute5: new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }),
    hour: new Intl.DateTimeFormat(undefined, {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }),
    day: new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "2-digit" }),
    month: new Intl.DateTimeFormat(undefined, { month: "2-digit", year: "numeric" }),
  };

  function formatTrafficChartLabels(data) {
    const labels = Array.isArray(data && data.labels) ? data.labels.slice() : [];
    const labelDatetimesUtc = Array.isArray(data && data.label_datetimes_utc)
      ? data.label_datetimes_utc
      : [];
    const bucket = String((data && data.bucket) || "").toLowerCase();
    const formatter = trafficLabelFormatters[bucket];
    if (!labels.length || labels.length !== labelDatetimesUtc.length || !formatter) {
      return labels;
    }
    return labels.map(function (fallbackLabel, index) {
      const parsed = new Date(labelDatetimesUtc[index]);
      if (Number.isNaN(parsed.getTime())) {
        return fallbackLabel;
      }
      return formatter.format(parsed);
    });
  }

  function formatLocalDateTimeCells(root) {
    const dtFormatter = new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll(".local-datetime[data-datetime]").forEach(function (cell) {
      const raw = cell.getAttribute("data-datetime") || cell.textContent;
      const parsed = parseServerDateTime(raw);
      if (!parsed) {
        return;
      }
      cell.textContent = dtFormatter.format(parsed);
      cell.title = `UTC: ${String(raw).trim()}`;
    });
  }

  function humanBytes(value) {
    let size = Number(value || 0);
    const units = ["B", "KB", "MB", "GB", "TB"];
    let idx = 0;
    while (size >= 1024 && idx < units.length - 1) {
      size /= 1024;
      idx += 1;
    }
    const precision = idx === 0 ? 0 : size < 10 ? 2 : 1;
    return `${size.toFixed(precision)} ${units[idx]}`;
  }

  window.LogsDashboardFmt = {
    parseProtocolTokens,
    protocolMatches,
    parseServerDateTime,
    formatLocalDateTimeCells,
    formatTrafficChartLabels,
    humanBytes,
  };
})();
