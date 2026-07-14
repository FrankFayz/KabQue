import { Outlet, useLocation } from 'react-router-dom';
import Brand from './Brand';
import NavBar from './NavBar';

export default function Layout() {
  const { pathname } = useLocation();
  const isHome = pathname === '/';

  return (
    <div className={`shell${isHome ? ' shell-home' : ''}`}>
      <header className="topbar">
        <Brand />
        <NavBar />
      </header>
      <main className={isHome ? 'main main-home' : 'main'}>
        <Outlet />
      </main>
      {!isHome && (
        <footer className="footer">
          <img src="/kabale-badge.png" alt="" width={28} height={28} />
          <span>KabQue · Kabale University · Knowledge is the Future</span>
        </footer>
      )}
    </div>
  );
}
