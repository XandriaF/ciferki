import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { api, downloadBlob } from "../api";

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

const ROLE_LABELS: Record<string, string> = {
  main: "Основной файл",
  demography: "Демография / панель",
  previous_wave: "Предыдущая волна",
};

const STEP_TYPE_LABELS: Record<string, string> = {
  match: "Мэтчинг",
  filter: "Фильтр",
  task: "Задача",
};

const FLAG_CLASS: Record<string, string> = {
  "выше": "flag-up",
  "ниже": "flag-down",
  "не значимо": "flag-neutral",
  "нет данных": "flag-none",
};

const NORM_LABELS: Record<string, string> = {
  q3: "Q3 по концептам файла",
  median: "медиана по концептам файла",
  manual: "фиксированная (вручную)",
  pool_q3: "Q3 по пулу волн",
  pool_median: "медиана по пулу волн",
};

const WAVE_MODE_LABELS: Record<string, string> = {
  independent: "полные выборки (независимые)",
  panel: "панель — одни и те же респонденты",
  panel_lag: "панель с окном по времени",
};

const fmtPct = (value: any) => (value === null || value === undefined ? "—" : `${String(value).replace(".", ",")}%`);
const fmtSigned = (value: any) =>
  value === null || value === undefined ? "—" : `${value > 0 ? "+" : ""}${String(value).replace(".", ",")}`;

export default function ProjectPage() {
  const { projectId } = useParams();
  const id = Number(projectId);

  const [meta, setMeta] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [needMatch, setNeedMatch] = useState(false);
  const needMatchTouched = useRef(false);
  const [uploadRole, setUploadRole] = useState("main");
  const fileRef = useRef<HTMLInputElement>(null);

  const [matchMainFile, setMatchMainFile] = useState("");
  const [matchDemoFile, setMatchDemoFile] = useState("");
  const [matchMainKey, setMatchMainKey] = useState("");
  const [matchDemoKey, setMatchDemoKey] = useState("");
  const [matchOnlyComplete, setMatchOnlyComplete] = useState(true);
  const [matchResult, setMatchResult] = useState<any>(null);

  const [stepColumn, setStepColumn] = useState("");
  const [stepOp, setStepOp] = useState("eq");
  const [stepValue, setStepValue] = useState("");
  const [stepValue2, setStepValue2] = useState("");
  const [values, setValues] = useState<any[]>([]);
  const [stepPreview, setStepPreview] = useState<any>(null);

  const [task, setTask] = useState("");
  const [conceptMap, setConceptMap] = useState<Record<string, string>>({});
  const [metrics, setMetrics] = useState<string[]>([]);
  const [normMode, setNormMode] = useState("q3");
  const [manualNorms, setManualNorms] = useState<Record<string, string>>({});
  const [taskResult, setTaskResult] = useState<any>(null);
  const [taskConfig, setTaskConfig] = useState<any>(null);

  const [waveMode, setWaveMode] = useState("independent");
  const [waveMainKey, setWaveMainKey] = useState("");
  const [wavePrevKey, setWavePrevKey] = useState("");
  const [waveMainDate, setWaveMainDate] = useState("");
  const [wavePrevDate, setWavePrevDate] = useState("");
  const [waveLagMin, setWaveLagMin] = useState("0");
  const [waveLagMax, setWaveLagMax] = useState("3650");
  const [prevConceptMap, setPrevConceptMap] = useState<Record<string, string>>({});
  const [metricMap, setMetricMap] = useState<Record<string, string>>({});
  const [waveResult, setWaveResult] = useState<any>(null);
  const [waveConfig, setWaveConfig] = useState<any>(null);

  const [analysisColumn, setAnalysisColumn] = useState("");
  const [freq, setFreq] = useState<any>(null);

  const load = async () => {
    try {
      const [projectMeta, projectData] = await Promise.all([api.project(id), api.projectData(id)]);
      setMeta(projectMeta);
      setData(projectData);
      setError("");
      if (!needMatchTouched.current) {
        setNeedMatch((projectMeta.files || []).length > 1);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить проект");
    }
  };

  useEffect(() => {
    load();
  }, [id]);

  const mainStructure = meta?.main_structure;
  const files: any[] = meta?.files || [];
  const prevFile = files.find((file) => file.role === "previous_wave");
  const prevStructure = prevFile?.structure || null;

  const matrixGroups = useMemo(() => {
    if (!mainStructure) return [] as string[];
    const groups: string[] = [];
    mainStructure.columns.forEach((column: any) => {
      if (column.type === "matrix" && column.group && !groups.includes(column.group)) groups.push(column.group);
    });
    return groups;
  }, [mainStructure]);

  const allMetrics = useMemo(() => {
    if (!mainStructure) return [] as string[];
    const list: string[] = [];
    mainStructure.columns.forEach((column: any) => {
      if (column.type === "matrix" && column.option && !list.includes(column.option)) list.push(column.option);
    });
    return list;
  }, [mainStructure]);

  useEffect(() => {
    if (matrixGroups.length && Object.keys(conceptMap).length === 0) {
      const initial: Record<string, string> = {};
      matrixGroups.forEach((group, index) => {
        initial[group] = `Концепт ${index + 1}`;
      });
      setConceptMap(initial);
    }
    if (allMetrics.length && metrics.length === 0) setMetrics(allMetrics);
  }, [matrixGroups, allMetrics]);

  const prevMatrixGroups = useMemo(() => {
    if (!prevStructure) return [] as string[];
    const groups: string[] = [];
    (prevStructure.columns || []).forEach((column: any) => {
      if (column.type === "matrix" && column.group && !groups.includes(column.group)) groups.push(column.group);
    });
    return groups;
  }, [prevStructure]);

  const prevMetrics = useMemo(() => {
    if (!prevStructure) return [] as string[];
    const list: string[] = [];
    (prevStructure.columns || []).forEach((column: any) => {
      if (column.type === "matrix" && column.option && !list.includes(column.option)) list.push(column.option);
    });
    return list;
  }, [prevStructure]);

  const mainColumns = useMemo(
    () => (mainStructure ? mainStructure.columns.map((column: any) => column.name) : []),
    [mainStructure]
  );
  const prevColumns = useMemo(
    () => (prevStructure ? (prevStructure.columns || []).map((column: any) => column.name) : []),
    [prevStructure]
  );

  useEffect(() => {
    if (!prevStructure || !prevMatrixGroups.length) return;
    setPrevConceptMap((current) => {
      if (Object.keys(current).length) return current;
      const initial: Record<string, string> = {};
      prevMatrixGroups.forEach((group, index) => {
        initial[group] = conceptMap[matrixGroups[index]] || `Концепт ${index + 1}`;
      });
      return initial;
    });
    setMetricMap((current) => {
      if (Object.keys(current).length) return current;
      const initial: Record<string, string> = {};
      allMetrics.forEach((metric) => {
        initial[metric] = prevMetrics.includes(metric) ? metric : "";
      });
      return initial;
    });
  }, [prevStructure, prevMatrixGroups, allMetrics, prevMetrics, conceptMap, matrixGroups]);

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
    if (!mainStructure) return [] as string[];
    return mainStructure.columns
      .filter((column: any) => column.type !== "service" && column.type !== "text")
      .map((column: any) => column.name);
  }, [mainStructure]);

  const analysisColumns = useMemo(() => {
    if (!mainStructure) return [] as string[];
    return mainStructure.columns.filter((column: any) => column.type !== "service").map((column: any) => column.name);
  }, [mainStructure]);

  const columnsOfFile = (fileId: string) => {
    const file = files.find((item) => String(item.id) === fileId);
    return (file?.structure?.columns || []).map((column: any) => column.name);
  };

  const attachFile = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Выберите файл");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const uploaded = await api.uploadFile(form);
      await api.addProjectFile(id, { upload_id: uploaded.id, role: uploadRole });
      if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось привязать файл");
    } finally {
      setBusy(false);
    }
  };

  const updateFileKey = async (fileId: number, key: string) => {
    try {
      await api.updateProjectFile(id, fileId, { key_column: key });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка сохранения ключа");
    }
  };

  const removeFile = async (fileId: number) => {
    if (!confirm("Убрать файл из проекта? В архиве он останется.")) return;
    try {
      await api.deleteProjectFile(id, fileId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка удаления файла");
    }
  };

  const checkMatch = async () => {
    try {
      const result = await api.matchPreview(id, {
        main_file_id: Number(matchMainFile),
        demo_file_id: Number(matchDemoFile),
        main_key: matchMainKey,
        demo_key: matchDemoKey,
        only_complete: matchOnlyComplete,
      });
      setMatchResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка проверки мэтчинга");
    }
  };

  const addMatchStep = async () => {
    try {
      await api.addStep(id, "match", {
        demo_file_id: Number(matchDemoFile),
        main_key: matchMainKey,
        demo_key: matchDemoKey,
        only_complete: matchOnlyComplete,
      });
      setMatchResult(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка шага мэтчинга");
    }
  };

  const params = () => {
    let value: any = stepValue;
    if (stepOp === "between") value = [stepValue, stepValue2];
    if (stepOp === "in") value = stepValue.split(",").map((item) => item.trim()).filter(Boolean);
    return { column: stepColumn, op: stepOp, value };
  };

  const checkStep = async () => {
    try {
      setStepPreview(await api.previewStep(id, params()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка проверки фильтра");
    }
  };

  const applyStep = async () => {
    setBusy(true);
    try {
      await api.addStep(id, "filter", params());
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

  const runTask = async () => {
    const config = { concept_map: conceptMap, metrics, norm_mode: normMode, manual_norms: manualNorms };
    setBusy(true);
    setError("");
    try {
      const response = await api.runTask(id, "top2_norms", config, true);
      setTaskResult(response.result);
      setTaskConfig(config);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка расчёта");
    } finally {
      setBusy(false);
    }
  };

  const rerunTask = async (step: any) => {
    const saved = step.params || {};
    try {
      const response = await api.runTask(id, saved.task, saved.config, false);
      if (saved.task === "wave_compare") {
        setTask("wave_compare");
        setWaveMode(saved.config.mode || "independent");
        setConceptMap(saved.config.concept_map || {});
        setPrevConceptMap(saved.config.prev_concept_map || {});
        setMetricMap(saved.config.metric_map || {});
        setMetrics(saved.config.metrics || []);
        setWaveMainKey(saved.config.main_key || "");
        setWavePrevKey(saved.config.prev_key || "");
        setWaveMainDate(saved.config.main_date || "");
        setWavePrevDate(saved.config.prev_date || "");
        setWaveLagMin(String(saved.config.lag_min_days ?? 0));
        setWaveLagMax(String(saved.config.lag_max_days ?? 3650));
        setWaveResult(response.result);
        setWaveConfig(saved.config);
        return;
      }
      setTask("top2_norms");
      setConceptMap(saved.config.concept_map || {});
      setMetrics(saved.config.metrics || []);
      setNormMode(saved.config.norm_mode || "q3");
      setManualNorms(saved.config.manual_norms || {});
      setTaskResult(response.result);
      setTaskConfig(saved.config);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка пересчёта");
    }
  };

  const exportTask = async () => {
    try {
      const blob = await api.exportProject(id, { task: { task: "top2_norms", config: taskConfig } });
      downloadBlob(blob, "ciferki_top2.xlsx");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка экспорта");
    }
  };

  const exportData = async () => {
    try {
      const blob = await api.exportProject(id, { column: analysisColumn || null });
      downloadBlob(blob, "ciferki_export.xlsx");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка экспорта");
    }
  };

  const buildWaveConfig = () => ({
    mode: waveMode,
    concept_map: conceptMap,
    prev_concept_map: prevConceptMap,
    metric_map: Object.fromEntries(Object.entries(metricMap).filter(([, value]) => value)),
    metrics,
    main_key: waveMainKey,
    prev_key: wavePrevKey,
    main_date: waveMainDate,
    prev_date: wavePrevDate,
    lag_min_days: Number(waveLagMin) || 0,
    lag_max_days: Number(waveLagMax) || 3650,
    alpha: 0.05,
  });

  const runWaveTask = async () => {
    const config = buildWaveConfig();
    setBusy(true);
    setError("");
    try {
      const response = await api.runTask(id, "wave_compare", config, true);
      setWaveResult(response.result);
      setWaveConfig(config);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка сравнения волн");
    } finally {
      setBusy(false);
    }
  };

  const exportWave = async () => {
    try {
      const blob = await api.exportProject(id, { task: { task: "wave_compare", config: waveConfig } });
      downloadBlob(blob, "ciferki_waves.xlsx");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка экспорта");
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

  const hasMainFile = files.some((file) => file.role === "main");
  const hasPrevWave = files.some((file) => file.role === "previous_wave");

  return (
    <div>
      {error && <div className="error">{error}</div>}

      <div className="card">
        <div className="project-head">
          <div>
            <h2>{meta.project.name}</h2>
            <p className="muted">
              Файлов: {files.length} · строк сейчас: <b>{meta.rows}</b>
              {hasMainFile ? ` · формат: ${mainStructure?.format}` : " · основной файл ещё не привязан"}
            </p>
          </div>
          <div className="row">
            <button className="secondary" onClick={exportData}>
              Excel: данные и шаги
            </button>
            {taskResult && (
              <button onClick={exportTask}>Excel с формулами (Top2)</button>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>1. Файлы проекта</h3>
        <div className="row">
          <label className="checkbox">
            <input
              type="radio"
              checked={!needMatch}
              onChange={() => {
                needMatchTouched.current = true;
                setNeedMatch(false);
              }}
            />{" "}
            Без мэтчинга — все файлы одного формата
          </label>
          <label className="checkbox">
            <input
              type="radio"
              checked={needMatch}
              onChange={() => {
                needMatchTouched.current = true;
                setNeedMatch(true);
              }}
            />{" "}
            Нужен мэтч — файлы с разных платформ
          </label>
        </div>
        <p className="muted">
          {needMatch
            ? "Загрузите минимум два файла: основной (анкета) и второй для мэтчинга (демография/панель). Затем выберите колонки-ключи и проверьте, сколько ID совпало."
            : "Загрузите файл выгрузки — он станет основным файлом проекта."}
        </p>
        <div className="row">
          <input type="file" ref={fileRef} accept=".csv,.txt,.xlsx" />
          <label>
            Роль файла
            <select value={uploadRole} onChange={(event) => setUploadRole(event.target.value)}>
              {Object.entries(ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button onClick={attachFile} disabled={busy}>
            {busy ? "Загружаем…" : "Загрузить и привязать"}
          </button>
        </div>

        {files.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Файл</th>
                <th>Роль</th>
                <th>Строк</th>
                <th>Колонка-ключ</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {files.map((file) => (
                <tr key={file.id}>
                  <td>{file.filename}</td>
                  <td>{ROLE_LABELS[file.role] || file.role}</td>
                  <td>{file.rows}</td>
                  <td>
                    <select value={file.key_column} onChange={(event) => updateFileKey(file.id, event.target.value)}>
                      <option value="">— не задана —</option>
                      {(file.structure?.columns || []).map((column: any) => (
                        <option key={column.index} value={column.name}>
                          {column.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="actions">
                    <button className="link danger" onClick={() => removeFile(file.id)}>
                      убрать
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {needMatch && files.length >= 2 && (
          <div className="match-block">
            <h4>Настройка мэтчинга</h4>
            <div className="row">
              <label>
                Основной файл
                <select
                  value={matchMainFile}
                  onChange={(event) => {
                    setMatchMainFile(event.target.value);
                    setMatchMainKey("");
                    setMatchResult(null);
                  }}
                >
                  <option value="">— выберите —</option>
                  {files.map((file) => (
                    <option key={file.id} value={file.id}>
                      {file.filename}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Ключ в основном
                <select value={matchMainKey} onChange={(event) => setMatchMainKey(event.target.value)}>
                  <option value="">— выберите —</option>
                  {columnsOfFile(matchMainFile).map((name: string) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Файл для мэтчинга
                <select
                  value={matchDemoFile}
                  onChange={(event) => {
                    setMatchDemoFile(event.target.value);
                    setMatchDemoKey("");
                    setMatchResult(null);
                  }}
                >
                  <option value="">— выберите —</option>
                  {files.map((file) => (
                    <option key={file.id} value={file.id}>
                      {file.filename}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Ключ в файле мэтчинга
                <select value={matchDemoKey} onChange={(event) => setMatchDemoKey(event.target.value)}>
                  <option value="">— выберите —</option>
                  {columnsOfFile(matchDemoFile).map((name: string) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={matchOnlyComplete}
                  onChange={(event) => setMatchOnlyComplete(event.target.checked)}
                />{" "}
                только complete
              </label>
              <button
                className="secondary"
                onClick={checkMatch}
                disabled={!matchMainFile || !matchDemoFile || !matchMainKey || !matchDemoKey}
              >
                Проверить
              </button>
            </div>
            {matchResult && (
              <div className="notice">
                Совпало ID: <b>{matchResult.matched}</b> · только в основном файле: {matchResult.only_main} · только в
                файле мэтчинга: {matchResult.only_demo}
                <div className="row" style={{ marginTop: 8 }}>
                  <button onClick={addMatchStep}>Добавить шаг мэтчинга</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {hasMainFile && (
        <div className="card">
          <h3>2. Что нужно сделать</h3>
          <div className="task-cards">
            <div
              className={`task-card ${task === "top2_norms" ? "active" : ""}`}
              onClick={() => setTask("top2_norms")}
            >
              <b>Концепты по метрикам и нормы</b>
              <p className="muted">
                Top2% по каждому концепту и метрике, 95% интервал Уилсона, сравнение с нормой (Q3 по концептам файла
                или вручную).
              </p>
            </div>
            <div
              className={`task-card ${task === "wave_compare" ? "active" : ""} ${hasPrevWave ? "" : "disabled"}`}
              onClick={() => hasPrevWave && setTask("wave_compare")}
            >
              <b>Сравнение с предыдущей волной</b>
              <p className="muted">
                {hasPrevWave
                  ? "Top2% обеих волн, разница и значимость: полные выборки, панель или панель с окном по времени."
                  : "Привяжите файл предыдущей волны (роль «Предыдущая волна») — задача станет доступна."}
              </p>
            </div>
          </div>

          {task === "top2_norms" && mainStructure && (
            <div className="task-config">
              <h4>Названия концептов (блоки анкеты)</h4>
              <div className="row">
                {matrixGroups.map((group) => (
                  <label key={group}>
                    {group}
                    <input
                      value={conceptMap[group] || ""}
                      onChange={(event) => setConceptMap({ ...conceptMap, [group]: event.target.value })}
                    />
                  </label>
                ))}
              </div>

              <h4>Метрики</h4>
              <div className="metrics-list">
                {allMetrics.map((metric) => (
                  <label key={metric} className="checkbox">
                    <input
                      type="checkbox"
                      checked={metrics.includes(metric)}
                      onChange={(event) =>
                        setMetrics(
                          event.target.checked ? [...metrics, metric] : metrics.filter((item) => item !== metric)
                        )
                      }
                    />{" "}
                    {metric}
                  </label>
                ))}
              </div>

              <h4>Норма</h4>
              <div className="row">
                <label className="checkbox">
                  <input type="radio" checked={normMode === "q3"} onChange={() => setNormMode("q3")} /> Q3 по концептам
                  файла
                </label>
                <label className="checkbox">
                  <input type="radio" checked={normMode === "median"} onChange={() => setNormMode("median")} /> Медиана
                  по концептам файла
                </label>
                <label className="checkbox">
                  <input type="radio" checked={normMode === "manual"} onChange={() => setNormMode("manual")} />{" "}
                  Фиксированная (вручную)
                </label>
                {hasPrevWave && (
                  <>
                    <label className="checkbox">
                      <input type="radio" checked={normMode === "pool_q3"} onChange={() => setNormMode("pool_q3")} /> Q3
                      по пулу волн
                    </label>
                    <label className="checkbox">
                      <input
                        type="radio"
                        checked={normMode === "pool_median"}
                        onChange={() => setNormMode("pool_median")}
                      />{" "}
                      Медиана по пулу волн
                    </label>
                  </>
                )}
              </div>
              {!hasPrevWave && (
                <p className="muted">
                  Норму по пулу волн можно посчитать, привязав к проекту файл предыдущей волны (роль «Предыдущая
                  волна»).
                </p>
              )}
              {normMode === "manual" && (
                <div className="row">
                  {metrics.map((metric) => (
                    <label key={metric}>
                      {metric}
                      <input
                        value={manualNorms[metric] || ""}
                        onChange={(event) => setManualNorms({ ...manualNorms, [metric]: event.target.value })}
                        placeholder="%"
                        style={{ width: 90 }}
                      />
                    </label>
                  ))}
                </div>
              )}

              <div className="row" style={{ marginTop: 12 }}>
                <button onClick={runTask} disabled={busy || !metrics.length}>
                  {busy ? "Считаем…" : "Рассчитать"}
                </button>
                {taskResult && (
                  <button className="secondary" onClick={exportTask}>
                    Excel с формулами
                  </button>
                )}
              </div>

              {taskResult && (
                <div className="analysis-result">
                  <p className="muted">
                    Норма: {NORM_LABELS[taskResult.norm_mode] || taskResult.norm_mode} · α = {taskResult.alpha} ·
                    Top2 = верхние 2 категории шкалы
                  </p>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Метрика</th>
                        <th>Концепт</th>
                        <th>N</th>
                        <th>Top2%</th>
                        <th>95% ДИ</th>
                        <th>Норма</th>
                        <th>Вывод</th>
                      </tr>
                    </thead>
                    <tbody>
                      {taskResult.metrics.map((metric: string) => (
                        <Fragment key={metric}>
                          <tr className="metric-row">
                            <td colSpan={7}>{metric}</td>
                          </tr>
                          {taskResult.concepts.map((concept: string) => {
                            const cell = taskResult.cells?.[concept]?.[metric];
                            if (!cell) return null;
                            return (
                              <tr key={`${concept}|${metric}`}>
                                <td></td>
                                <td>{concept}</td>
                                <td>{cell.n}</td>
                                <td>{cell.pct === null ? "—" : String(cell.pct).replace(".", ",")}</td>
                                <td>
                                  {cell.lower === null
                                    ? "—"
                                    : `[${String(cell.lower).replace(".", ",")}; ${String(cell.upper).replace(".", ",")}]`}
                                </td>
                                <td>{cell.norm === null ? "—" : String(cell.norm).replace(".", ",")}</td>
                                <td>
                                  <span className={`flag ${FLAG_CLASS[cell.flag] || "flag-none"}`}>{cell.flag}</span>
                                </td>
                              </tr>
                            );
                          })}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {task === "wave_compare" && mainStructure && prevStructure && (
            <div className="task-config">
              <h4>Режим сравнения</h4>
              <div className="row">
                <label className="checkbox">
                  <input
                    type="radio"
                    checked={waveMode === "independent"}
                    onChange={() => setWaveMode("independent")}
                  />{" "}
                  Полные выборки (независимые)
                </label>
                <label className="checkbox">
                  <input type="radio" checked={waveMode === "panel"} onChange={() => setWaveMode("panel")} /> Одни и те
                  же респонденты (панель)
                </label>
                <label className="checkbox">
                  <input
                    type="radio"
                    checked={waveMode === "panel_lag"}
                    onChange={() => setWaveMode("panel_lag")}
                  />{" "}
                  Панель с окном по времени
                </label>
              </div>

              {waveMode !== "independent" && (
                <div className="row">
                  <label>
                    Ключ — текущая волна
                    <select value={waveMainKey} onChange={(event) => setWaveMainKey(event.target.value)}>
                      <option value="">— выберите —</option>
                      {mainColumns.map((name: string) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Ключ — прошлая волна
                    <select value={wavePrevKey} onChange={(event) => setWavePrevKey(event.target.value)}>
                      <option value="">— выберите —</option>
                      {prevColumns.map((name: string) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {waveMode === "panel_lag" && (
                    <>
                      <label>
                        Дата — текущая
                        <select value={waveMainDate} onChange={(event) => setWaveMainDate(event.target.value)}>
                          <option value="">— выберите —</option>
                          {mainColumns.map((name: string) => (
                            <option key={name} value={name}>
                              {name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Дата — прошлая
                        <select value={wavePrevDate} onChange={(event) => setWavePrevDate(event.target.value)}>
                          <option value="">— выберите —</option>
                          {prevColumns.map((name: string) => (
                            <option key={name} value={name}>
                              {name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Лаг от, дней
                        <input
                          value={waveLagMin}
                          onChange={(event) => setWaveLagMin(event.target.value)}
                          style={{ width: 90 }}
                        />
                      </label>
                      <label>
                        до, дней
                        <input
                          value={waveLagMax}
                          onChange={(event) => setWaveLagMax(event.target.value)}
                          style={{ width: 90 }}
                        />
                      </label>
                    </>
                  )}
                </div>
              )}

              <h4>Концепты прошлой волны</h4>
              <div className="row">
                {prevMatrixGroups.map((group) => (
                  <label key={group}>
                    {group}
                    <input
                      value={prevConceptMap[group] || ""}
                      onChange={(event) => setPrevConceptMap({ ...prevConceptMap, [group]: event.target.value })}
                    />
                  </label>
                ))}
              </div>

              <h4>Сопоставление метрик (текущая → прошлая)</h4>
              <div className="metrics-list">
                {metrics.map((metric) => (
                  <label key={metric} className="metric-map-row">
                    {metric}
                    <select
                      value={metricMap[metric] ?? ""}
                      onChange={(event) => setMetricMap({ ...metricMap, [metric]: event.target.value })}
                    >
                      <option value="">— не сопоставлена —</option>
                      {prevMetrics.map((prevMetric) => (
                        <option key={prevMetric} value={prevMetric}>
                          {prevMetric}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>

              <div className="row" style={{ marginTop: 12 }}>
                <button onClick={runWaveTask} disabled={busy || !metrics.length}>
                  {busy ? "Считаем…" : "Сравнить волны"}
                </button>
                {waveResult && (
                  <button className="secondary" onClick={exportWave}>
                    Excel с формулами
                  </button>
                )}
              </div>

              {waveResult && (
                <div className="analysis-result">
                  <p className="muted">
                    Режим: {WAVE_MODE_LABELS[waveResult.mode] || waveResult.mode} · α = {waveResult.alpha}
                    {waveResult.matched_total !== null &&
                      ` · совпало ID: ${waveResult.matched_total}, в расчёте: ${waveResult.matched_used}`}
                    {waveResult.lag &&
                      ` · окно лага: ${waveResult.lag.min}–${waveResult.lag.max} дн., медиана ${
                        waveResult.lag.median_days ?? "—"
                      }, исключено ${waveResult.lag.excluded}`}
                  </p>
                  {(waveResult.warnings || []).map((warning: string, index: number) => (
                    <div key={index} className="notice">
                      {warning}
                    </div>
                  ))}
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Метрика</th>
                        <th>N₁</th>
                        <th>Top2 волна 1</th>
                        <th>N₂</th>
                        <th>Top2 волна 2</th>
                        <th>Разница</th>
                        <th>95% ДИ разницы</th>
                        {waveResult.mode !== "independent" && <th>↑ / ↓</th>}
                        <th>p</th>
                        <th>Вывод</th>
                      </tr>
                    </thead>
                    <tbody>
                      {waveResult.concepts.map((concept: string) => {
                        const conceptCells = waveResult.cells?.[concept] || {};
                        const metricsWithData = waveResult.metrics.filter((metric: string) => conceptCells[metric]);
                        if (!metricsWithData.length) return null;
                        return (
                          <Fragment key={concept}>
                            <tr className="metric-row">
                              <td colSpan={waveResult.mode !== "independent" ? 10 : 9}>{concept}</td>
                            </tr>
                            {metricsWithData.map((metric: string) => {
                              const cell = conceptCells[metric];
                              return (
                                <tr key={`${concept}|${metric}`}>
                                  <td>{metric}</td>
                                  <td>{cell.n1}</td>
                                  <td>{fmtPct(cell.p1)}</td>
                                  <td>{cell.n2}</td>
                                  <td>{fmtPct(cell.p2)}</td>
                                  <td>{fmtSigned(cell.diff)}</td>
                                  <td>
                                    {cell.lower === null
                                      ? "—"
                                      : `[${String(cell.lower).replace(".", ",")}; ${String(cell.upper).replace(
                                          ".",
                                          ","
                                        )}]`}
                                  </td>
                                  {waveResult.mode !== "independent" && (
                                    <td>
                                      {cell.b} / {cell.c}
                                    </td>
                                  )}
                                  <td>{cell.p_value === null ? "—" : String(cell.p_value).replace(".", ",")}</td>
                                  <td>
                                    <span className={`flag ${FLAG_CLASS[cell.flag] || "flag-none"}`}>{cell.flag}</span>
                                  </td>
                                </tr>
                              );
                            })}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="workspace">
        <div>
          <div className="card">
            <h3>История шагов</h3>
            {meta.history.length === 0 && <p className="muted">Пока шагов нет — данные в исходном виде.</p>}
            {meta.history.map((step: any) => (
              <div key={step.id} className="step-item">
                <div className="step-line">
                  <span>
                    <b>{STEP_TYPE_LABELS[step.type] || step.type}.</b> {step.summary}
                  </span>
                  <span className="actions">
                    {step.type === "task" && (
                      <button className="link" onClick={() => rerunTask(step)}>
                        показать
                      </button>
                    )}
                    <button className="link danger" onClick={() => undo(step.id)}>
                      вернуться
                    </button>
                  </span>
                </div>
                {step.type !== "task" && (
                  <div className="muted">
                    строк: {step.rows_before} → {step.rows_after}
                  </div>
                )}
              </div>
            ))}
          </div>

          {hasMainFile && (
            <div className="card">
              <h3>Очистка выборки</h3>
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
                <div className="row">
                  <button className="secondary" onClick={checkStep} disabled={!stepColumn}>
                    Проверить
                  </button>
                  <button onClick={applyStep} disabled={!stepColumn || busy}>
                    Применить
                  </button>
                </div>
                {stepPreview && (
                  <div className="notice">
                    Останется строк: {stepPreview.rows_after} из {stepPreview.rows_before}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div>
          {hasMainFile && (
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
          )}

          {hasMainFile && (
            <div className="card">
              <h3>Частоты по колонке</h3>
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
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
