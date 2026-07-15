import { Link } from 'react-router-dom';

export default function Hero() {
  return (
    <section className="cover" aria-label="KabQue — Kabale University fresher queue">
      <div className="cover-media" aria-hidden="true">
        <img
          src="/kabale-campus-building.png"
          alt=""
          className="cover-photo"
        />
        <div className="cover-veil" />
        <div className="cover-grain" />
      </div>

      <div className="cover-frame">
        <div className="cover-copy">
          <p className="cover-uni">Kabale University</p>
          <h1 className="cover-brand">KabQue</h1>
          <span className="cover-rule" aria-hidden="true" />
          <p className="cover-lede">
            The official fresher document queue for Kikungiri Campus — fair
            order, clear alerts, calm intake.
          </p>
          <div className="cover-cta">
            <Link to="/register" className="btn btn-header-create cover-btn-create">
              Create account
            </Link>
            <Link to="/login" className="btn btn-cover-secondary">
              Sign in
            </Link>
          </div>
          <p className="cover-motto">Knowledge is the Future</p>
        </div>
      </div>
    </section>
  );
}
