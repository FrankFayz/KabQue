import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { getStoredUser } from './api';
import { homePathFor, isMainAdmin } from './authRoles';
import AuthShell from './components/auth/AuthShell';
import Layout from './components/layout/Layout';
import Home from './pages/Home';
import Login from './pages/Login';
import Register from './pages/Register';
import StudentDashboard from './pages/StudentDashboard';
import AdminDashboard from './pages/AdminDashboard';
import MainAdminDashboard from './pages/MainAdminDashboard';
import './App.css';

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
    if (isMainAdmin(user)) return children;
    if (user.role !== 'admin' && !user.is_staff) {
      return <Navigate to="/student" replace />;
    }
    if (user.is_approved === false) {
      return <Navigate to="/login" replace />;
    }
    return children;
  }

  if (role === 'student') {
    if (isMainAdmin(user)) {
      return <Navigate to="/main-admin" replace />;
    }
    if (user.role === 'admin' || user.role === 'main_admin') {
      return <Navigate to="/admin" replace />;
    }
    return children;
  }

  return children;
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
