import { Link, Outlet, useLocation } from 'react-router-dom';
import AuthShowcase from './AuthShowcase';

export default function AuthShell() {
  const { pathname } = useLocation();
  const onLogin = pathname.includes('login');
  const onRegister = pathname.includes('register');

  return (
    <div className="auth-shell">
      <header className="auth-top">
        <Link to="/" className="auth-wordmark" aria-label="KabQue home">
          <img
            className="auth-wordmark-badge"
            src="/kabale-badge.png"
            alt="Kabale University badge"
            width={44}
            height={44}
          />
          <span className="auth-wordmark-text">
            <span className="auth-wordmark-name">KabQue</span>
            <span className="auth-wordmark-sub">Kabale University queue</span>
          </span>
        </Link>
        <nav className="auth-top-nav" aria-label="Account">
          <Link
            to="/login"
            className={`btn btn-header-signin${onLogin ? ' is-active' : ''}`}
            aria-current={onLogin ? 'page' : undefined}
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className={`btn btn-header-create${onRegister ? ' is-active' : ''}`}
            aria-current={onRegister ? 'page' : undefined}
          >
            Create account
          </Link>
        </nav>
      </header>

      <div className="auth-grid">
        <AuthShowcase />
        <section className="auth-panel-wrap">
          <Outlet />
        </section>
      </div>

      <footer className="auth-footer">
        <div className="auth-footer-inner">
          <img
            src="/kabale-badge.png"
            alt=""
            width={32}
            height={32}
            className="auth-footer-badge"
          />
          <div className="auth-footer-copy">
            <p className="auth-footer-brand">
              KabQue · Kabale University · Knowledge is the Future
            </p>
            <p className="auth-footer-meta">
              Kikungiri Campus ·{' '}
              <Link to="/">Home</Link>
              {' · '}
              <a href="https://www.kab.ac.ug/" target="_blank" rel="noopener noreferrer">
                kab.ac.ug
              </a>
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
