import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .projects()
      .then((data) => setProjects(data.projects))
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить проекты"));
  }, []);

  return (
    <div className="card">
      <h2>Проекты</h2>
      <p className="muted">
        Проект — это загруженный файл и цепочка шагов обработки. Внутри видна история шагов, можно вернуться к
        любому из них и скачать результат в Excel с формулами.
      </p>
      {error && <div className="error">{error}</div>}
      <table className="table">
        <thead>
          <tr>
            <th>Название</th>
            <th>Файл</th>
            <th>Автор</th>
            <th>Шагов</th>
            <th>Создан</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr key={project.id}>
              <td>{project.name}</td>
              <td>{project.filename}</td>
              <td>{project.author}</td>
              <td>{project.steps_count}</td>
              <td>{new Date(project.created_at).toLocaleString("ru-RU")}</td>
              <td>
                <Link to={`/project/${project.id}`}>Открыть</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {projects.length === 0 && !error && (
        <p className="muted">Пока проектов нет — загрузите файл в разделе «Данные».</p>
      )}
    </div>
  );
}
