import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { getStoredUser } from './api';
import AuthShell from './components/auth/AuthShell';
import Layout from './components/layout/Layout';
import Home from './pages/Home';
import Login from './pages/Login';
import Register from './pages/Register';
import StudentDashboard from './pages/StudentDashboard';
import AdminDashboard from './pages/AdminDashboard';
import './App.css';

function Protected({ children, role }) {
  const user = getStoredUser();
  if (!user) return <Navigate to="/login" replace />;
  if (role === 'admin' && user.role !== 'admin' && !user.is_staff) {
    return <Navigate to="/student" replace />;
  }
  if (role === 'student' && user.role === 'admin') {
    return <Navigate to="/admin" replace />;
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
        </Route>

        <Route element={<AuthShell />}>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
