import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { api } from "../api";

const OP_OPTIONS = [
  { value: "eq", label: "равно" },
  { value: "ne", label: "не равно" },
  { value: "in", label: "входит в список" },
  { value: "gt", label: "больше" },
  { value: "lt", label: "меньше" },
  { value: "between", label: "в диапазоне" },
  { value: "not_empty", label: "заполнено" },
  { value: "empty", label: "пусто" },
];

export default function ProjectPage() {
  const { projectId } = useParams();
  const id = Number(projectId);

  const [meta, setMeta] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [stepColumn, setStepColumn] = useState("");
  const [stepOp, setStepOp] = useState("eq");
  const [stepValue, setStepValue] = useState("");
  const [stepValue2, setStepValue2] = useState("");
  const [values, setValues] = useState<any[]>([]);
  const [stepPreview, setStepPreview] = useState<any>(null);

  const [analysisColumn, setAnalysisColumn] = useState("");
  const [freq, setFreq] = useState<any>(null);

  const load = async () => {
    try {
      const [projectMeta, projectData] = await Promise.all([api.project(id), api.projectData(id)]);
      setMeta(projectMeta);
      setData(projectData);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить проект");
    }
  };

  useEffect(() => {
    load();
  }, [id]);

  useEffect(() => {
    setStepPreview(null);
    if (!stepColumn) {
      setValues([]);
      return;
    }
    api
      .projectValues(id, stepColumn)
      .then((result) => setValues(result.values))
      .catch(() => setValues([]));
  }, [stepColumn, id]);

  const filterColumns = useMemo(() => {
    if (!meta) return [] as string[];
    return meta.structure.columns
      .filter((column: any) => column.type !== "service" && column.type !== "text")
      .map((column: any) => column.name);
  }, [meta]);

  const analysisColumns = useMemo(() => {
    if (!meta) return [] as string[];
    return meta.structure.columns.filter((column: any) => column.type !== "service").map((column: any) => column.name);
  }, [meta]);

  const params = () => {
    let value: any = stepValue;
    if (stepOp === "between") value = [stepValue, stepValue2];
    if (stepOp === "in") value = stepValue.split(",").map((item) => item.trim()).filter(Boolean);
    return { column: stepColumn, op: stepOp, value };
  };

  const check = async () => {
    try {
      setStepPreview(await api.previewStep(id, params()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка проверки фильтра");
    }
  };

  const apply = async () => {
    setBusy(true);
    try {
      await api.addStep(id, params());
      setStepPreview(null);
      setStepValue("");
      setStepValue2("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка применения фильтра");
    } finally {
      setBusy(false);
    }
  };

  const undo = async (stepId: number) => {
    if (!confirm("Вернуться к состоянию до этого шага? Последующие шаги будут удалены.")) return;
    try {
      await api.deleteStep(id, stepId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка отката");
    }
  };

  const analyze = async () => {
    if (!analysisColumn) return;
    try {
      setFreq(await api.frequencies(id, analysisColumn));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка расчёта");
    }
  };

  const gridColumns: ColDef[] = useMemo(() => {
    if (!data) return [];
    return data.columns.map((name: string, index: number) => ({
      headerName: name,
      field: String(index),
      width: 150,
      sortable: true,
      resizable: true,
    }));
  }, [data]);

  const gridRows = useMemo(() => {
    if (!data) return [];
    return data.rows.map((row: any[]) => {
      const obj: any = {};
      row.forEach((value, index) => {
        obj[String(index)] = value;
      });
      return obj;
    });
  }, [data]);

  if (!meta || !data) {
    return <div className="card">{error || "Загрузка…"}</div>;
  }

  return (
    <div>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <div className="project-head">
          <div>
            <h2>{meta.project.name}</h2>
            <p className="muted">
              Файл: {meta.upload?.filename} · формат: {meta.structure.format} · строк сейчас:{" "}
              <b>{meta.rows}</b>
              {meta.upload?.rows ? ` (в исходном файле: ${meta.upload.rows})` : ""}
            </p>
          </div>
          <div className="row">
            <a className="button" href={api.exportUrl(id, analysisColumn || undefined)}>
              Скачать Excel
            </a>
          </div>
        </div>
      </div>

      <div className="workspace">
        <div className="card">
          <h3>История шагов</h3>
          {meta.history.length === 0 && <p className="muted">Пока шагов нет — данные в исходном виде.</p>}
          <ol className="steps">
            {meta.history.map((step: any) => (
              <li key={step.id}>
                <div className="step-line">
                  <span>{step.summary}</span>
                  <button className="link danger" onClick={() => undo(step.id)}>
                    вернуться
                  </button>
                </div>
                <div className="muted">
                  строк: {step.rows_before} → {step.rows_after}
                </div>
              </li>
            ))}
          </ol>

          <h3>Новый шаг — фильтр</h3>
          <div className="stack">
            <label>
              Колонка
              <select value={stepColumn} onChange={(event) => setStepColumn(event.target.value)}>
                <option value="">— выберите —</option>
                {filterColumns.map((name: string) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Условие
              <select value={stepOp} onChange={(event) => setStepOp(event.target.value)}>
                {OP_OPTIONS.map((op) => (
                  <option key={op.value} value={op.value}>
                    {op.label}
                  </option>
                ))}
              </select>
            </label>
            {!["not_empty", "empty"].includes(stepOp) && (
              <label>
                Значение
                {stepOp === "between" ? (
                  <div className="row">
                    <input value={stepValue} onChange={(event) => setStepValue(event.target.value)} placeholder="от" />
                    <input value={stepValue2} onChange={(event) => setStepValue2(event.target.value)} placeholder="до" />
                  </div>
                ) : (
                  <input
                    list="step-values"
                    value={stepValue}
                    onChange={(event) => setStepValue(event.target.value)}
                    placeholder={stepOp === "in" ? "значения через запятую" : "значение"}
                  />
                )}
                <datalist id="step-values">
                  {values.map((item) => (
                    <option key={String(item.value)} value={String(item.value)} />
                  ))}
                </datalist>
              </label>
            )}
            {values.length > 0 && stepOp === "eq" && (
              <p className="muted">
                Частые значения: {values.slice(0, 6).map((item) => `${item.value} (${item.n})`).join(", ")}
              </p>
            )}
            <div className="row">
              <button className="secondary" onClick={check} disabled={!stepColumn}>
                Проверить
              </button>
              <button onClick={apply} disabled={!stepColumn || busy}>
                Применить
              </button>
            </div>
            {stepPreview && (
              <div className="notice">
                Останется строк: {stepPreview.rows_after} из {stepPreview.rows_before}
                {stepPreview.rows_after === 0 && " — фильтр удалит все данные, проверьте условие"}
              </div>
            )}
          </div>
        </div>

        <div>
          <div className="card">
            <h3>
              Текущие данные (первые {Math.min(200, data.total)} из {data.total})
            </h3>
            <div className="ag-theme-quartz grid-wrap">
              <AgGridReact
                rowData={gridRows}
                columnDefs={gridColumns}
                defaultColDef={{ sortable: true, resizable: true }}
                domLayout="autoHeight"
              />
            </div>
          </div>

          <div className="card">
            <h3>Анализ колонки</h3>
            <div className="row">
              <label>
                Колонка
                <select value={analysisColumn} onChange={(event) => setAnalysisColumn(event.target.value)}>
                  <option value="">— выберите —</option>
                  {analysisColumns.map((name: string) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <button onClick={analyze} disabled={!analysisColumn}>
                Показать
              </button>
              {freq && (
                <a className="button secondary" href={api.exportUrl(id, analysisColumn)}>
                  Excel с формулами
                </a>
              )}
            </div>
            {freq && (
              <div className="analysis-result">
                <p className="muted">
                  {freq.column_meta?.label ? `${freq.column_meta.label}. ` : ""}
                  Всего строк: {freq.total_rows}, валидных ответов: {freq.valid}
                </p>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Значение</th>
                      <th>N</th>
                      <th>% от валидных</th>
                    </tr>
                  </thead>
                  <tbody>
                    {freq.rows.map((row: any, index: number) => (
                      <tr key={index}>
                        <td>{String(row.value)}</td>
                        <td>{row.n}</td>
                        <td>{row.pct.toFixed(1).replace(".", ",")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {freq.stats && (
                  <p className="muted">
                    Среднее: {String(freq.stats.mean).replace(".", ",")} · медиана:{" "}
                    {String(freq.stats.median).replace(".", ",")} · SD: {String(freq.stats.sd).replace(".", ",")} · мин:{" "}
                    {String(freq.stats.min).replace(".", ",")} · макс: {String(freq.stats.max).replace(".", ",")}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
