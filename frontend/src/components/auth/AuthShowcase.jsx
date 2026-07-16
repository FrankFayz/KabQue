import { Link } from 'react-router-dom';

export default function AuthShowcase() {
  return (
    <aside className="auth-showcase" aria-label="KabQue introduction">
      <div className="auth-showcase-media" aria-hidden="true">
        <img src="/kabale-campus-building.png" alt="" />
        <div className="auth-showcase-overlay" />
      </div>

      <div className="auth-showcase-content">
        <p className="auth-kicker">Kabale University</p>
        <h2 className="auth-showcase-title">KabQue</h2>
        <span className="auth-showcase-rule" aria-hidden="true" />
        <p className="auth-showcase-lede">
          Ordered fresher queues at Kikungiri — clear alerts, fair intake, calm
          verification.
        </p>
        <p className="auth-showcase-motto">Knowledge is the Future</p>
        <p className="auth-showcase-foot">
          <Link to="/">Home</Link>
          <span aria-hidden="true"> · </span>
          <a href="https://www.kab.ac.ug/" target="_blank" rel="noreferrer">
            kab.ac.ug
          </a>
        </p>
      </div>
    </aside>
  );
}
