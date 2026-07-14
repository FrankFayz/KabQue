import { Link, useNavigate } from 'react-router-dom';
import { clearAuth, getStoredUser } from '../../api';
import { isMainAdmin } from '../../authRoles';

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
          {user.role === 'student' && (
            <Link to="/student" className="nav-link">
              My queue
            </Link>
          )}
          {isMainAdmin(user) && (
            <>
              <Link to="/main-admin" className="nav-link">
                Main Admin
              </Link>
              <Link to="/main-admin" className="nav-link">
                Students
              </Link>
              <Link to="/admin" className="nav-link">
                Supervisors
              </Link>
            </>
          )}
          {!isMainAdmin(user) && (user.role === 'admin' || user.is_staff) && (
            <Link to="/admin" className="nav-link">
              Desk
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
