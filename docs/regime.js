// 시장 국면 대시보드 — docs/data/market_regime.json 을 fetch 하여 표로 렌더링.
// GitHub Actions 크론이 JSON을 갱신하므로, 이 페이지는 순수 정적(브라우저)에서 동작한다.

function fmtNum(n) {
  if (n === null || n === undefined) return "-";
  return Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(n) {
  if (n === null || n === undefined) return "-";
  const sign = n >= 0 ? "+" : "−";
  return sign + Math.abs(Number(n)).toFixed(2) + "%";
}

function renderRegime(data) {
  const body = document.getElementById("regime-body");
  const rows = (data && data.indices) || [];
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="4" class="muted" style="text-align:center;padding:24px;">데이터가 없습니다.</td></tr>';
    return;
  }

  body.innerHTML = rows.map(function (r) {
    let state, pctClass;
    if (r.ok) {
      if (r.is_bull) { state = '<span class="bull">🟢 상승장</span>'; pctClass = "bull"; }
      else { state = '<span class="bear">🔴 하락장</span>'; pctClass = "bear"; }
      if (r.stale) state += ' <span class="stale">(이전값)</span>';
    } else {
      state = '<span class="muted">⚪ 조회 실패</span>';
      pctClass = "muted";
    }
    const price = r.ok ? fmtNum(r.price) : "-";
    const pct = r.ok ? '<span class="' + pctClass + '">' + fmtPct(r.diff_pct) + "</span>" : '<span class="muted">-</span>';
    return (
      "<tr>" +
      '<td style="font-weight:600;">' + (r.flag || "") + " " + r.name + "</td>" +
      '<td style="text-align:center;">' + state + "</td>" +
      '<td class="num">' + price + "</td>" +
      '<td class="num">' + pct + "</td>" +
      "</tr>"
    );
  }).join("");

  const updated = document.getElementById("regime-updated");
  const mw = data.ma_window || 200;
  updated.textContent = "기준: " + mw + "일 이동평균선 · 갱신: " + (data.generated_at_kst || data.generated_at_utc || "-");
}

function loadRegime() {
  const body = document.getElementById("regime-body");
  body.innerHTML = '<tr><td colspan="4" class="muted" style="text-align:center;padding:24px;">데이터를 불러오는 중…</td></tr>';
  // 캐시 무력화를 위해 쿼리 파라미터 부여
  fetch("data/market_regime.json?t=" + Date.now())
    .then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    })
    .then(renderRegime)
    .catch(function (err) {
      body.innerHTML =
        '<tr><td colspan="4" class="muted" style="text-align:center;padding:24px;">' +
        "데이터를 불러오지 못했습니다: " + err.message + "</td></tr>";
    });
}

document.addEventListener("DOMContentLoaded", loadRegime);
