import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { api } from "../api";

const TYPE_LABELS: Record<string, string> = {
  service: "служебная",
  numeric: "числовая",
  categorical: "категориальная",
  choice: "выбор (да/нет)",
  matrix: "шкала (matrix)",
  text: "текст",
};

export default function UploadPreview() {
  const { uploadId } = useParams();
  const navigate = useNavigate();
  const [payload, setPayload] = useState<any>(null);
  const [types, setTypes] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .uploadPreview(Number(uploadId))
      .then((data) => {
        setPayload(data);
        setName(data.filename.replace(/\.[^.]+$/, ""));
        const initial: Record<string, string> = {};
        data.structure.columns.forEach((column: any) => {
          initial[column.name] = column.type;
        });
        setTypes(initial);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Ошибка загрузки"));
  }, [uploadId]);

  const gridColumns: ColDef[] = useMemo(() => {
    if (!payload) return [];
    return payload.structure.columns.map((column: any, index: number) => ({
      headerName: column.name,
      field: String(index),
      width: 150,
    }));
  }, [payload]);

  const gridRows = useMemo(() => {
    if (!payload) return [];
    return payload.preview.map((row: string[]) => {
      const obj: any = {};
      row.forEach((value, index) => {
        obj[String(index)] = value;
      });
      return obj;
    });
  }, [payload]);

  const create = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await api.createProject({ name, upload_id: Number(uploadId), settings: { types } });
      navigate(`/project/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать проект");
    } finally {
      setBusy(false);
    }
  };

  if (!payload) return <div className="card">{error || "Загрузка…"}</div>;

  return (
    <div>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <h2>Предпросмотр: {payload.filename}</h2>
        <p className="muted">
          Формат: {payload.structure.format} · строк данных: {payload.structure.rows} · колонок:{" "}
          {payload.structure.columns.length}
        </p>
        <div className="row">
          <label>
            Название проекта
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <button onClick={create} disabled={busy || !name.trim()}>
            {busy ? "Создаём…" : "Создать проект"}
          </button>
          <Link className="button secondary" to="/">
            Назад к данным
          </Link>
        </div>
      </div>

      <div className="card">
        <h3>Колонки и типы</h3>
        <p className="muted">
          Проверьте, как сервис распознал колонки. Тип можно изменить — от него зависят доступные расчёты.
        </p>
        <div className="columns-table">
          <table className="table">
            <thead>
              <tr>
                <th>Колонка</th>
                <th>Текст вопроса</th>
                <th>Группа</th>
                <th>Тип</th>
              </tr>
            </thead>
            <tbody>
              {payload.structure.columns.map((column: any) => (
                <tr key={column.index}>
                  <td>{column.name}</td>
                  <td className="muted">{column.label || column.option || ""}</td>
                  <td>{column.group || ""}</td>
                  <td>
                    <select
                      value={types[column.name] || column.type}
                      onChange={(event) => setTypes({ ...types, [column.name]: event.target.value })}
                    >
                      {Object.entries(TYPE_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>Первые строки данных</h3>
        <div className="ag-theme-quartz grid-wrap">
          <AgGridReact
            rowData={gridRows}
            columnDefs={gridColumns}
            defaultColDef={{ resizable: true }}
            domLayout="autoHeight"
          />
        </div>
      </div>
    </div>
  );
}
