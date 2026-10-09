const $ = (id) => document.getElementById(id);
const COLORS = ["#684a37", "#211b17", "#a98568", "#806a58", "#bea58e"];
const LABELS = {
  total_return: "Total return", annualized_return: "Annualized return",
  annualized_volatility: "Annualized volatility", sharpe_ratio: "Sharpe ratio",
  sortino_ratio: "Sortino ratio", max_drawdown: "Max drawdown"
};
const METRIC_DESCRIPTIONS = {
  total_return: "Compounded change over the full sample.",
  annualized_return: "Compounded return scaled to 252 trading days.",
  annualized_volatility: "Daily return variation scaled to a year.",
  sharpe_ratio: "Excess return per unit of volatility.",
  sortino_ratio: "Excess return per unit of downside variation.",
  max_drawdown: "Largest decline from a previous high."
};
const MODEL_NAMES = {
  capm: "Benchmark regression", ff3: "Fama–French 3-factor",
  ff5: "Fama–French 5-factor", momentum: "Momentum factor", carhart: "Carhart 4-factor"
};
let currentFile = null;
let report = null;
let selectedRange = "ALL";
let selectedModel = "ff5";
let sampleDataSelected = false;
let selectionVersion = 0;
let analysisVersion = 0;

const pct = (value, digits = 1) => value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
const num = (value, digits = 2) => value == null ? "—" : Number(value).toFixed(digits);
const signed = (value, digits = 3) => value == null ? "—" : `${value >= 0 ? "+" : ""}${Number(value).toFixed(digits)}`;
const shortDate = (date) => new Date(`${date}T00:00:00`).toLocaleDateString(undefined, {month:"short", year:"numeric"});
const longDate = (date) => new Date(`${date}T00:00:00`).toLocaleDateString(undefined, {day:"numeric", month:"short", year:"numeric"});
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[character]);

function showNotice(message, type = "error") {
  const notice = $("notice");
  notice.textContent = message;
  notice.className = `notice ${type}`;
  notice.hidden = false;
}
function clearNotice() { $("notice").hidden = true; }
function setStatus(message, mode = "") {
  const status = $("side-status");
  status.className = `status ${mode}`;
  status.textContent = message;
}
function resetQuiz() {
  $("sample-quiz").hidden = true;
  $("quiz-answer").value = "";
  $("quiz-answer").disabled = false;
  $("quiz-form").querySelector('button[type="submit"]').disabled = false;
  $("quiz-reveal").hidden = false;
  $("quiz-feedback").textContent = "";
  $("quiz-feedback").className = "quiz-feedback";
}
function chooseFile(file, sample = false) {
  if (!file) return;
  selectionVersion++;
  analysisVersion++;
  currentFile = file;
  sampleDataSelected = sample;
  report = null;
  $("report").hidden = true;
  resetQuiz();
  $("run-button").disabled = false;
  setStatus(sample ? "Sample data ready to analyze." : `${file.name} is ready to analyze.`, "ready");
  clearNotice();
}

async function loadSample() {
  const version = ++selectionVersion;
  const button = $("sample-button");
  button.disabled = true;
  try {
    const response = await fetch("/sample.csv");
    if (!response.ok) throw new Error("The sample dataset could not be loaded.");
    const file = new File([await response.blob()], "sample-returns.csv", {type:"text/csv"});
    if (version !== selectionVersion) return;
    $("csv-file").value = "";
    chooseFile(file, true);
    await runAnalysis();
  } catch (error) {
    if (version === selectionVersion) showNotice(error.message);
  } finally {
    button.disabled = false;
  }
}

async function runAnalysis() {
  if (!currentFile) return;
  const version = ++analysisVersion;
  const file = currentFile;
  const sample = sampleDataSelected;
  const button = $("run-button");
  button.disabled = true;
  button.textContent = "Analyzing…";
  resetQuiz();
  setStatus("Analyzing returns and factor data…", "ready");
  clearNotice();
  try {
    const response = await fetch(`/api/analyze?window=${$("window").value}`, {
      method: "POST", headers: {"Content-Type": "text/csv"}, body: file
    });
    const payload = await response.json();
    if (version !== analysisVersion) return;
    if (!response.ok) throw new Error(payload.error || "Analysis failed.");
    report = payload;
    $("report").hidden = false;
    renderReport();
    $("sample-quiz").hidden = !sample;
    setStatus(`${payload.overview.observations.toLocaleString()} rows analyzed`, "ready");
    if (payload.overview.warnings.length) showNotice(payload.overview.warnings.join(" "), "info");
  } catch (error) {
    if (version !== analysisVersion) return;
    setStatus("Analysis failed", "error");
    showNotice(error.message);
  } finally {
    if (version === analysisVersion) {
      button.disabled = false;
      button.textContent = "Run analysis";
    }
  }
}

function renderMetrics() {
  const p = report.metrics.portfolio;
  const b = report.metrics.benchmark;
  const cards = [
    ["total_return", pct],
    ["annualized_return", pct],
    ["annualized_volatility", pct],
    ["sharpe_ratio", num],
    ["sortino_ratio", num],
    ["max_drawdown", pct],
  ];
  const html = cards.map(([key, format]) => {
    return `<div class="metric-card"><h3>${LABELS[key]}</h3><p class="metric-value">${format(p[key])}</p><p class="metric-benchmark">Benchmark: ${format(b[key])}</p><p class="metric-description">${METRIC_DESCRIPTIONS[key]}</p></div>`;
  }).join("");
  $("metric-grid").innerHTML = html;
}

function svgNode(name, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}
function textNode(svg, x, y, content, attributes = {}) {
  const node = svgNode("text", {x, y, class:"axis-label", ...attributes});
  node.textContent = content;
  svg.appendChild(node);
}
function rangeStart(dates) {
  if (selectedRange === "ALL" || !dates.length) return 0;
  const end = new Date(`${dates[dates.length - 1]}T00:00:00Z`);
  end.setUTCFullYear(end.getUTCFullYear() - (selectedRange === "1Y" ? 1 : 5));
  const cutoff = end.toISOString().slice(0, 10);
  const index = dates.findIndex((date) => date >= cutoff);
  return index < 0 ? 0 : index;
}
function valueLabel(value, mode) {
  if (value == null) return "—";
  if (mode === "percent") return pct(value);
  if (mode === "wealth") return `$${num(value, 2)}`;
  return num(value, 2);
}

function drawLineChart(id, payload, mode, area = false) {
  const container = $(id);
  container.replaceChildren();
  if (!payload?.dates?.length || !Object.keys(payload.series || {}).length) {
    container.innerHTML = '<div class="chart-empty">Rolling betas are not available for this model.</div>';
    return;
  }
  const width = Math.max(container.clientWidth, 320);
  const height = Math.max(container.clientHeight - 23, 170);
  const left = 55, right = width - 15, top = 14, bottom = height - 29;
  const start = rangeStart(payload.dates);
  const dates = payload.dates.slice(start);
  const names = Object.keys(payload.series);
  const values = names.flatMap((name) => payload.series[name].slice(start).filter((value) => value != null));
  if (!values.length) {
    container.innerHTML = '<div class="chart-empty">No observations in this range.</div>';
    return;
  }
  let low = Infinity, high = -Infinity;
  for (const value of values) { if (value < low) low = value; if (value > high) high = value; }
  if (mode === "percent" && high <= 0) high = 0;
  if (mode === "wealth") low = 0;
  const pad = Math.max((high - low) * .09, mode === "wealth" ? .05 : .01);
  if (mode !== "wealth") low -= pad;
  high += pad;
  const y = (value) => top + (high - value) / (high - low) * (bottom - top);
  const x = (index) => left + index / Math.max(dates.length - 1, 1) * (right - left);
  const svg = svgNode("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":id.replaceAll("-", " ")});

  for (let tick = 0; tick <= 4; tick++) {
    const value = low + (high - low) * (1 - tick / 4);
    const yy = top + (bottom - top) * tick / 4;
    svg.appendChild(svgNode("line", {x1:left, y1:yy, x2:right, y2:yy, class:"grid-line"}));
    textNode(svg, left - 8, yy + 4, valueLabel(value, mode), {"text-anchor":"end"});
  }
  if (low < 0 && high > 0) svg.appendChild(svgNode("line", {x1:left, y1:y(0), x2:right, y2:y(0), class:"zero-line"}));
  for (let tick = 0; tick <= 4; tick++) {
    const index = Math.round((dates.length - 1) * tick / 4);
    textNode(svg, x(index), height - 6, shortDate(dates[index]), {"text-anchor":tick === 0 ? "start" : tick === 4 ? "end" : "middle"});
  }

  const stride = Math.max(1, Math.ceil(dates.length / 1000));
  names.forEach((name, colorIndex) => {
    const series = payload.series[name].slice(start);
    const sample = [];
    for (let index = 0; index < series.length; index += stride) sample.push(index);
    if (sample[sample.length - 1] !== series.length - 1) sample.push(series.length - 1);
    let path = "", first = null, last = null;
    for (const index of sample) {
      const value = series[index];
      if (value == null) { last = null; continue; }
      const point = [x(index), y(value)];
      path += `${last ? "L" : "M"}${point[0].toFixed(1)},${point[1].toFixed(1)}`;
      first ||= point; last = point;
    }
    if (area && colorIndex === 0 && first && last) {
      const fill = svgNode("path", {d:`${path} L${last[0]},${bottom} L${first[0]},${bottom} Z`, fill:"rgba(104,74,55,.12)"});
      svg.appendChild(fill);
    }
    svg.appendChild(svgNode("path", {d:path, stroke:COLORS[colorIndex % COLORS.length], class:`chart-path ${colorIndex ? "secondary" : ""}`}));
  });

  const hoverLine = svgNode("line", {y1:top, y2:bottom, class:"hover-line", visibility:"hidden"});
  svg.appendChild(hoverLine);
  const hit = svgNode("rect", {x:left, y:top, width:right-left, height:bottom-top, fill:"transparent"});
  svg.appendChild(hit);
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.hidden = true;
  hit.addEventListener("mousemove", (event) => {
    const bounds = svg.getBoundingClientRect();
    const localX = (event.clientX - bounds.left) * width / bounds.width;
    const index = Math.max(0, Math.min(dates.length - 1, Math.round((localX - left) / (right - left) * (dates.length - 1))));
    hoverLine.setAttribute("x1", x(index)); hoverLine.setAttribute("x2", x(index)); hoverLine.setAttribute("visibility", "visible");
    tooltip.innerHTML = `<strong>${longDate(dates[index])}</strong>${names.map((name, i) => `<div class="tip-row"><span><i class="tip-dot" style="background:${COLORS[i % COLORS.length]}"></i>${escapeHtml(name)}</span><b>${valueLabel(payload.series[name][start + index], mode)}</b></div>`).join("")}`;
    tooltip.hidden = false;
    tooltip.style.left = `${Math.min(Math.max(event.clientX - container.getBoundingClientRect().left + 12, 6), container.clientWidth - tooltip.offsetWidth - 5)}px`;
    tooltip.style.top = `${Math.max(5, event.clientY - container.getBoundingClientRect().top - tooltip.offsetHeight - 10)}px`;
  });
  hit.addEventListener("mouseleave", () => {tooltip.hidden = true; hoverLine.setAttribute("visibility", "hidden");});
  container.appendChild(svg);
  const legend = document.createElement("div");
  legend.className = "chart-legend";
  names.forEach((name, index) => {
    const item = document.createElement("span");
    const dot = document.createElement("i");
    dot.style.background = COLORS[index % COLORS.length];
    item.append(dot, document.createTextNode(name));
    legend.appendChild(item);
  });
  container.append(legend, tooltip);
}

function drawHistogram() {
  const container = $("histogram-chart");
  container.replaceChildren();
  const raw = report.charts.daily_returns;
  const all = [...raw.portfolio, ...raw.benchmark].filter((value) => value != null);
  if (!all.length) return;
  let min = Infinity, max = -Infinity;
  for (const value of all) { if (value < min) min = value; if (value > max) max = value; }
  const bins = 30, span = max - min || 1;
  const counts = [raw.portfolio, raw.benchmark].map((series) => {
    const output = Array(bins).fill(0);
    series.forEach((value) => {if (value != null) output[Math.min(bins - 1, Math.floor((value - min) / span * bins))]++;});
    return output;
  });
  const peak = Math.max(...counts[0], ...counts[1]);
  const width = Math.max(container.clientWidth, 320), height = Math.max(container.clientHeight - 23, 160);
  const left = 50, right = width - 14, top = 9, bottom = height - 27, binWidth = (right - left) / bins;
  const svg = svgNode("svg", {viewBox:`0 0 ${width} ${height}`, role:"img", "aria-label":"Daily return distribution"});
  for (let tick = 0; tick <= 3; tick++) {
    const yy = top + (bottom - top) * tick / 3;
    svg.appendChild(svgNode("line", {x1:left,y1:yy,x2:right,y2:yy,class:"grid-line"}));
    textNode(svg,left-8,yy+4,String(Math.round(peak*(1-tick/3))),{"text-anchor":"end"});
  }
  for (let index = 0; index < bins; index++) {
    counts.forEach((series, group) => {
      const barHeight = series[index] / peak * (bottom - top);
      svg.appendChild(svgNode("rect", {
        x:left + index * binWidth + group * binWidth * .42 + 1,
        y:bottom - barHeight, width:Math.max(1,binWidth * .4 - 1), height:barHeight,
        fill:COLORS[group], opacity:group ? .7 : .9, rx:1
      }));
    });
  }
  for (let tick = 0; tick <= 4; tick++) {
    textNode(svg,left+(right-left)*tick/4,height-5,pct(min+span*tick/4,0),{"text-anchor":tick===0?"start":tick===4?"end":"middle"});
  }
  container.appendChild(svg);
  const legend = document.createElement("div"); legend.className = "chart-legend";
  legend.innerHTML = `<span><i style="background:${COLORS[0]}"></i>Portfolio</span><span><i style="background:${COLORS[1]}"></i>Benchmark</span>`;
  container.appendChild(legend);
}

function renderModel() {
  const regression = report.regressions[selectedModel];
  $("model-title").textContent = MODEL_NAMES[selectedModel];
  $("model-alpha").textContent = pct(regression.alpha_annualized, 2);
  $("model-r2").textContent = pct(regression.r_squared);
  $("model-nobs").textContent = regression.observations.toLocaleString();
  const loadings = regression.loadings.filter((loading) => loading.name !== "Alpha");
  const max = Math.max(.01, ...loadings.map((loading) => Math.abs(loading.coef || 0)));
  $("factor-bars").innerHTML = loadings.map((loading) => {
    const width = Math.abs(loading.coef || 0) / max * 46;
    const left = loading.coef < 0 ? 50 - width : 50;
    return `<div class="factor-row"><span class="name">${escapeHtml(loading.name)}</span><span class="bar-track"><span class="factor-fill ${loading.coef < 0 ? "negative" : ""}" style="left:${left}%;width:${width}%"></span></span><span class="value">${signed(loading.coef)}</span></div>`;
  }).join("");
  $("factor-table").innerHTML = regression.loadings.map((loading) => `<tr><td>${escapeHtml(loading.name)}${loading.significant ? '<i class="sig-dot" title="p < 0.05"></i>' : ""}</td><td>${signed(loading.coef,4)}</td><td>${num(loading.tstat)}</td><td>${loading.pvalue == null ? "—" : loading.pvalue < .0001 ? "<0.0001" : num(loading.pvalue,4)}</td></tr>`).join("");
  const rolling = report.charts.rolling_betas[selectedModel];
  drawLineChart("betas-chart", rolling, "ratio");
  document.querySelectorAll("[data-model]").forEach((button) => {
    const selected = button.dataset.model === selectedModel;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-selected", String(selected));
  });
}

function renderData() {
  const overview = report.overview;
  $("period-label").textContent = `${longDate(overview.start)} — ${longDate(overview.end)}`;
  $("row-pill").textContent = `${overview.observations.toLocaleString()} observations`;
  $("window-pill").textContent = `${overview.window}-day rolling window`;
  $("sharpe-window").textContent = `${overview.window}-day window`;
  $("beta-window").textContent = `${overview.window}-day window`;
  $("factor-source").textContent = overview.factor_source;
  const dates = report.charts.wealth.dates;
  const daily = report.charts.daily_returns;
  const rows = [];
  for (let index = dates.length - 1; index >= Math.max(0, dates.length - 8); index--) {
    rows.push(`<tr><td>${dates[index]}</td><td>${pct(daily.portfolio[index],2)}</td><td>${pct(daily.benchmark[index],2)}</td></tr>`);
  }
  $("returns-table").innerHTML = rows.join("");
}

function renderCharts() {
  drawLineChart("wealth-chart", report.charts.wealth, "wealth", true);
  drawLineChart("drawdown-chart", report.charts.drawdown, "percent", true);
  drawLineChart("sharpe-chart", {dates:report.charts.rolling_sharpe.dates, series:{Sharpe:report.charts.rolling_sharpe.values}}, "ratio");
  drawHistogram();
  renderModel();
}
function renderReport() { renderData(); renderMetrics(); renderCharts(); }

function revealQuizAnswer(message) {
  $("quiz-feedback").textContent = message;
  $("quiz-feedback").className = "quiz-feedback correct";
  $("quiz-answer").disabled = true;
  $("quiz-form").querySelector('button[type="submit"]').disabled = true;
  $("quiz-reveal").hidden = true;
}

$("quiz-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const guess = $("quiz-answer").value.toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (["QQQ", "INVESCOQQQ", "INVESCOQQQTRUST"].includes(guess)) {
    revealQuizAnswer("Correct — the sample portfolio is QQQ. Growth and factor exposure can support a guess, but they are not a unique identifier.");
  } else {
    $("quiz-feedback").textContent = "Not quite. Compare the growth chart and factor coefficients, then try again.";
    $("quiz-feedback").className = "quiz-feedback incorrect";
  }
});
$("quiz-reveal").addEventListener("click", () => {
  revealQuizAnswer("The sample portfolio is QQQ. Growth and factor exposure are useful clues, though they cannot identify an ETF with certainty.");
});

$("csv-file").addEventListener("change", (event) => chooseFile(event.target.files[0]));
$("window").addEventListener("input", (event) => {
  $("window-value").textContent = `${event.target.value} days`;
  if (report) setStatus("Window changed · run analysis", "");
});
$("run-button").addEventListener("click", runAnalysis);
$("sample-button").addEventListener("click", loadSample);
document.querySelectorAll("[data-range]").forEach((button) => button.addEventListener("click", () => {
  selectedRange = button.dataset.range;
  document.querySelectorAll("[data-range]").forEach((item) => item.classList.toggle("selected", item === button));
  if (report) {renderCharts();}
}));
document.querySelectorAll("[data-model]").forEach((button) => button.addEventListener("click", () => {
  selectedModel = button.dataset.model;
  if (report) renderModel();
}));
let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {if (report) renderCharts();}, 150);
});
