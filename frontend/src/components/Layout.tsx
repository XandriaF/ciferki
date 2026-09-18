import { Link, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export default function Layout() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // ignore
    }
    setUser(null);
    navigate("/login");
  };

  return (
    <div>
      <header className="topbar">
        <div className="container topbar-inner">
          <div className="brand">Циферки</div>
          <nav className="nav">
            <Link to="/">Данные</Link>
            <Link to="/projects">Проекты</Link>
            {user?.is_admin && <Link to="/users">Пользователи</Link>}
          </nav>
          <div className="user-box">
            <span className="muted">{user?.display_name}</span>
            <button className="link" onClick={logout}>
              Выйти
            </button>
          </div>
        </div>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </div>
  );
}
