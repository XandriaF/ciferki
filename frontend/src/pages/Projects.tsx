import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const load = async () => {
    try {
      const data = await api.projects();
      setProjects(data.projects);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить проекты");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!newName.trim()) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.createProject({ name: newName.trim() });
      navigate(`/project/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать проект");
    } finally {
      setBusy(false);
    }
  };

  const rename = async (id: number, current: string) => {
    const name = prompt("Новое название проекта", current);
    if (!name || !name.trim() || name.trim() === current) return;
    try {
      await api.renameProject(id, name.trim());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка переименования");
    }
  };

  const remove = async (id: number, name: string) => {
    if (!confirm(`Удалить проект «${name}»? Файлы останутся в архиве, но шаги и настройки проекта удалятся.`)) return;
    try {
      await api.deleteProject(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка удаления");
    }
  };

  return (
    <div>
      <div className="card">
        <h2>Новый проект</h2>
        <p className="muted">
          Начните с названия — дальше в проекте загрузите файлы (с мэтчингом или без) и выберите, что нужно
          посчитать.
        </p>
        <div className="row">
          <label>
            Название проекта
            <input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="Например: ФРК8, волна 3"
              onKeyDown={(event) => event.key === "Enter" && create()}
            />
          </label>
          <button onClick={create} disabled={busy || !newName.trim()}>
            {busy ? "Создаём…" : "Начать проект"}
          </button>
        </div>
        {error && <div className="error">{error}</div>}
      </div>

      <div className="card">
        <h2>Мои проекты</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Название</th>
              <th>Основной файл</th>
              <th>Автор</th>
              <th>Файлов</th>
              <th>Шагов</th>
              <th>Создан</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {projects.map((project) => (
              <tr key={project.id}>
                <td>{project.name}</td>
                <td>{project.filename || "—"}</td>
                <td>{project.author}</td>
                <td>{project.files_count}</td>
                <td>{project.steps_count}</td>
                <td>{new Date(project.created_at).toLocaleString("ru-RU")}</td>
                <td className="actions">
                  <Link to={`/project/${project.id}`}>Открыть</Link>
                  <button className="link" onClick={() => rename(project.id, project.name)}>
                    Переименовать
                  </button>
                  <button className="link danger" onClick={() => remove(project.id, project.name)}>
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {projects.length === 0 && !error && <p className="muted">Пока проектов нет — создайте первый выше.</p>}
      </div>
    </div>
  );
}
