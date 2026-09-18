import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { api } from "../api";

type UploadRow = {
  id: number;
  filename: string;
  size: number;
  rows: number | null;
  columns: number | null;
  uploaded_at: string;
  uploader: string | null;
  uploader_name: string | null;
};

const formatSize = (bytes: number) =>
  bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`;

const formatDate = (iso: string) => new Date(iso).toLocaleString("ru-RU");

export default function DataPage() {
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastUpload, setLastUpload] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      const data = await api.uploads();
      setRows(data.uploads as UploadRow[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить архив");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Выберите файл");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    setLastUpload(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const data = await api.uploadFile(form);
      if (fileRef.current) fileRef.current.value = "";
      await load();
      setLastUpload(data.id);
      setNotice(`Загружено: ${data.filename} (${data.rows} строк, ${data.columns} колонок)`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки");
    } finally {
      setBusy(false);
    }
  };

  const columnDefs: ColDef<UploadRow>[] = [
    { field: "uploaded_at", headerName: "Дата", valueFormatter: (p) => formatDate(p.value), width: 170 },
    { field: "filename", headerName: "Файл", flex: 2 },
    { field: "uploader_name", headerName: "Загрузил", flex: 1 },
    { field: "rows", headerName: "Строк", width: 100 },
    { field: "columns", headerName: "Колонок", width: 110 },
    { field: "size", headerName: "Размер", width: 110, valueFormatter: (p) => formatSize(p.value) },
    {
      headerName: "",
      width: 220,
      sortable: false,
      filter: false,
      cellRenderer: (p: any) => (
        <span className="row-links">
          <Link to={`/upload/${p.data.id}`}>Настроить</Link>
          <a href={`/api/uploads/${p.data.id}/download`}>Скачать</a>
        </span>
      ),
    },
  ];

  return (
    <div>
      <div className="card">
        <h2>Загрузка данных</h2>
        <p className="muted">
          Файлы сохраняются в архиве — видно, кто и когда загрузил. После загрузки откроется предпросмотр: там
          можно проверить колонки, задать типы и создать проект для пошагового анализа.
        </p>
        <div className="row">
          <input type="file" ref={fileRef} accept=".csv,.txt,.xlsx" />
          <button onClick={upload} disabled={busy}>
            {busy ? "Загружаем…" : "Загрузить в архив"}
          </button>
        </div>
        {error && <div className="error">{error}</div>}
        {notice && (
          <div className="notice">
            {notice}{" "}
            {lastUpload && (
              <Link className="notice-link" to={`/upload/${lastUpload}`}>
                Настроить и создать проект →
              </Link>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <h2>Архив данных</h2>
        <div className="ag-theme-quartz grid-wrap">
          <AgGridReact
            rowData={rows}
            columnDefs={columnDefs}
            defaultColDef={{ sortable: true, resizable: true }}
            domLayout="autoHeight"
          />
        </div>
      </div>
    </div>
  );
}
