import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { getStoredUser } from './api';
import {
  homePathFor,
  isMainAdmin,
  isStudent,
  isSupervisor,
} from './authRoles';
import AuthShell from './components/auth/AuthShell';
import Layout from './components/layout/Layout';
import Home from './pages/Home';
import Login from './pages/Login';
import Register from './pages/Register';
import StudentDashboard from './pages/StudentDashboard';
import AdminDashboard from './pages/AdminDashboard';
import MainAdminDashboard from './pages/MainAdminDashboard';
import './App.css';
import './responsive.css';

/**
 * Strict role gates:
 * - student      → /student only
 * - supervisor   → /admin only
 * - main_admin   → /main-admin only
 * Cross-role URLs bounce to that user's home.
 */
function Protected({ children, role }) {
  const user = getStoredUser();
  if (!user) return <Navigate to="/login" replace />;

  if (role === 'main_admin') {
    if (!isMainAdmin(user)) {
      return <Navigate to={homePathFor(user)} replace />;
    }
    return children;
  }

  if (role === 'admin') {
    if (!isSupervisor(user)) {
      return <Navigate to={homePathFor(user)} replace />;
    }
    return children;
  }

  if (role === 'student') {
    if (!isStudent(user)) {
      return <Navigate to={homePathFor(user)} replace />;
    }
    return children;
  }

  return <Navigate to={homePathFor(user)} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route
            path="/student"
            element={
              <Protected role="student">
                <StudentDashboard />
              </Protected>
            }
          />
          <Route
            path="/admin"
            element={
              <Protected role="admin">
                <AdminDashboard />
              </Protected>
            }
          />
          <Route
            path="/main-admin"
            element={
              <Protected role="main_admin">
                <MainAdminDashboard />
              </Protected>
            }
          />
        </Route>

        <Route element={<AuthShell />}>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
