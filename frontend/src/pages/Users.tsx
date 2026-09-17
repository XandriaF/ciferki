import { useEffect, useState, type FormEvent } from "react";
import { api } from "../api";

type UserRow = {
  id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
  created_at: string;
};

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const data = await api.users();
      setUsers(data.users as UserRow[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить список");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createUser({ username, display_name: displayName, password, is_admin: isAdmin });
      setUsername("");
      setDisplayName("");
      setPassword("");
      setIsAdmin(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка создания");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    if (!confirm("Удалить пользователя?")) return;
    try {
      await api.deleteUser(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка удаления");
    }
  };

  return (
    <div>
      <div className="card">
        <h2>Добавить участника</h2>
        <p className="muted">Участники видят архив и загружают данные под своим логином — в архиве сохраняется, кто загрузил файл.</p>
        <form className="row" onSubmit={create}>
          <label>
            Логин
            <input value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label>
            Имя
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Как показывать в архиве"
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
            />
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} /> Администратор
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "Создаём…" : "Создать"}
          </button>
        </form>
        {error && <div className="error">{error}</div>}
      </div>

      <div className="card">
        <h2>Пользователи</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Логин</th>
              <th>Имя</th>
              <th>Роль</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.username}</td>
                <td>{user.display_name}</td>
                <td>{user.is_admin ? "Администратор" : "Участник"}</td>
                <td>
                  <button className="link danger" onClick={() => remove(user.id)}>
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
