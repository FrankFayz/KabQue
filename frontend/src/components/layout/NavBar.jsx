import { Link, useNavigate } from 'react-router-dom';
import { clearAuth, getStoredUser } from '../../api';
import { isMainAdmin, isStudent, isSupervisor } from '../../authRoles';

export default function NavBar() {
  const user = getStoredUser();
  const navigate = useNavigate();

  function logout() {
    clearAuth();
    navigate('/');
  }

  return (
    <nav className="nav" aria-label="Primary">
      {!user && (
        <div className="nav-actions">
          <Link to="/login" className="btn btn-header-signin">
            Sign in
          </Link>
          <Link to="/register" className="btn btn-header-create">
            Create account
          </Link>
        </div>
      )}

      {user && (
        <div className="nav-actions">
          {isStudent(user) && (
            <Link to="/student" className="nav-link">
              My queue
            </Link>
          )}
          {isSupervisor(user) && (
            <Link to="/admin" className="nav-link">
              Desk
            </Link>
          )}
          {isMainAdmin(user) && (
            <Link to="/main-admin" className="nav-link">
              Main Admin
            </Link>
          )}
          <button type="button" className="btn btn-header-signin" onClick={logout}>
            Sign out
          </button>
        </div>
      )}
    </nav>
  );
}
