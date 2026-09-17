const fileInput = document.getElementById("file");
const fileInfo = document.getElementById("file-info");
const setupSection = document.getElementById("step-setup");
const resultSection = document.getElementById("step-result");
const resultEl = document.getElementById("result");
const errorEl = document.getElementById("error");
const valueSelect = document.getElementById("value-col");
const groupSelect = document.getElementById("group-col");
const alphaSelect = document.getElementById("alpha");
const runButton = document.getElementById("run");

let currentFile = null;

const esc = (value) =>
  String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const fmt = (value, digits = 2) =>
  value === null || value === undefined || Number.isNaN(value) ? "—" : Number(value).toFixed(digits).replace(".", ",");

const fmtP = (p) =>
  p === null || p === undefined || Number.isNaN(p) ? "—" : p < 0.001 ? "< 0,001" : "= " + Number(p).toFixed(3).replace(".", ",");

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove("hidden");
}

function hideError() {
  errorEl.classList.add("hidden");
  errorEl.textContent = "";
}

function errorMessage(payload, fallback) {
  if (payload && typeof payload.detail === "string") return payload.detail;
  return fallback;
}

fileInput.addEventListener("change", async () => {
  currentFile = fileInput.files[0] || null;
  resultSection.classList.add("hidden");
  hideError();
  if (!currentFile) return;
  fileInfo.textContent = `${currentFile.name} — читаем…`;
  const form = new FormData();
  form.append("file", currentFile);
  try {
    const response = await fetch("/api/columns", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(errorMessage(data, "Не удалось прочитать файл"));
    fileInfo.textContent = `${currentFile.name}: строк — ${data.rows}, столбцов — ${data.columns.length}`;
    fillSelects(data.columns);
    setupSection.classList.remove("hidden");
  } catch (error) {
    currentFile = null;
    fileInfo.textContent = "";
    setupSection.classList.add("hidden");
    showError(error.message || "Ошибка соединения с сервером");
  }
});

function fillSelects(columns) {
  valueSelect.innerHTML = "";
  groupSelect.innerHTML = "";
  for (const column of columns) {
    valueSelect.append(new Option(column.name, column.name));
    groupSelect.append(new Option(column.name, column.name));
  }
  const numeric = columns.filter((column) => /int|float/.test(column.dtype));
  const other = columns.filter((column) => !/int|float/.test(column.dtype));
  if (numeric.length) valueSelect.value = numeric[0].name;
  if (other.length) groupSelect.value = other[0].name;
  else if (columns.length > 1) groupSelect.value = columns[1].name;
}

runButton.addEventListener("click", async () => {
  if (!currentFile) return;
  hideError();
  runButton.disabled = true;
  runButton.textContent = "Считаем…";
  const form = new FormData();
  form.append("file", currentFile);
  form.append("value_col", valueSelect.value);
  form.append("group_col", groupSelect.value);
  form.append("alpha", alphaSelect.value);
  try {
    const response = await fetch("/api/ttest", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(errorMessage(data, "Ошибка расчёта"));
    render(data);
    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showError(error.message || "Ошибка соединения с сервером");
  } finally {
    runButton.disabled = false;
    runButton.textContent = "Рассчитать";
  }
});

function tableBlock(title, headers, rows) {
  const head = headers.map((header) => `<th>${esc(header)}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("");
  return `<div class="block"><h3>${esc(title)}</h3><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function badge(ok, textOk, textWarn) {
  return `<span class="badge ${ok ? "badge-ok" : "badge-warn"}">${ok ? textOk : textWarn}</span>`;
}

function assumptionsHtml(assumptions) {
  const normalityRows = assumptions.normality.groups.map((group) => [
    esc(group.group),
    fmt(group.W, 3),
    fmtP(group.p),
  ]);
  const normalityVerdict = badge(assumptions.normality.passed, "пройдена", "не пройдена");
  const homogeneityVerdict = badge(assumptions.homogeneity.passed, "пройдена", "не пройдена");
  const body = normalityRows
    .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("");
  return `
    <div class="block">
      <h3>Проверка допущений</h3>
      <p class="muted">Нормальность распределения (тест Шапиро–Уилка): ${normalityVerdict}</p>
      <table>
        <thead><tr><th>Группа</th><th>W</th><th>p</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
      <p class="muted">Однородность дисперсий (тест Левена по медиане, Браун–Форсайт): F = ${fmt(assumptions.homogeneity.statistic, 3)}, p ${fmtP(assumptions.homogeneity.p)} — ${homogeneityVerdict}</p>
    </div>`;
}

function testBlock(title, result) {
  let rows;
  if (result.t !== undefined) {
    rows = [
      ["Тест", esc(result.name)],
      ["t", fmt(result.t, 3)],
      ["Степени свободы (df)", fmt(result.df, 2)],
      ["p", fmtP(result.p)],
      ["Разность средних (M₁ − M₂)", fmt(result.mean_diff, 3)],
      ["95% доверительный интервал", `[${fmt(result.ci[0], 3)}; ${fmt(result.ci[1], 3)}]`],
      ["d Коэна", `${fmt(result.cohens_d, 3)} (${esc(result.effect)})`],
      ["g Хеджеса", fmt(result.hedges_g, 3)],
    ];
  } else {
    rows = [
      ["Тест", esc(result.name)],
      ["U", fmt(result.u, 1)],
      ["p", fmtP(result.p)],
      ["Разность медиан", fmt(result.median_diff, 3)],
      ["Рангово-бисериальная корреляция", `${fmt(result.rank_biserial, 3)} (${esc(result.effect)})`],
    ];
  }
  return tableBlock(title, ["Показатель", "Значение"], rows);
}

function procedureHtml(procedure) {
  const steps = procedure.steps
    .map(
      (step) => `
      <div class="step">
        <h4>${esc(step.title)}</h4>
        <p>${esc(step.text)}</p>
        ${step.decision ? `<p class="decision"><strong>Решение:</strong> ${esc(step.decision)}</p>` : ""}
      </div>`
    )
    .join("");
  const references = procedure.references.map((ref) => `<li>${esc(ref)}</li>`).join("");
  return `
    <details class="block procedure">
      <summary>Как это считалось: процедура, решения и обоснования</summary>
      ${steps}
      <h4>Литература</h4>
      <ul class="refs">${references}</ul>
    </details>`;
}

function render(data) {
  resultEl.innerHTML = `
    <div class="callout ${data.significant ? "callout-ok" : "callout-neutral"}">
      <strong>Вывод.</strong> ${esc(data.conclusion)}
    </div>
    ${tableBlock(
      "Описательные статистики",
      ["Группа", "n", "Среднее", "SD", "Медиана", "Мин", "Макс"],
      data.descriptives.map((row) => [
        esc(row.group),
        row.n,
        fmt(row.mean),
        fmt(row.sd),
        fmt(row.median),
        fmt(row.min),
        fmt(row.max),
      ])
    )}
    ${assumptionsHtml(data.assumptions)}
    ${testBlock("Основной результат", data.primary)}
    ${data.reference ? testBlock("Справочный результат (t-тест, для сведения)", data.reference) : ""}
    ${procedureHtml(data.procedure)}
  `;
}
