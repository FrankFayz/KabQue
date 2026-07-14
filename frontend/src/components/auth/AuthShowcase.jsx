import { Link } from 'react-router-dom';
import { KAB_RESOURCES } from '../../constants/kabResources';

export default function AuthShowcase() {
  return (
    <aside className="auth-showcase">
      <div className="auth-showcase-media">
        <img
          src="/kabale-campus-building.png"
          alt="Kabale University Teaching Facility 1 at Kikungiri Campus"
        />
        <div className="auth-showcase-overlay" />
      </div>

      <div className="auth-showcase-content">
        <p className="auth-kicker">Kabale University · Kikungiri Campus</p>
        <h2 className="auth-showcase-title">Knowledge is the Future</h2>
        <p className="auth-showcase-lede">
          KabQue runs document approval with a fair campus queue — sign in to continue.
        </p>

        <div className="auth-resource-block">
          <h3>University resources</h3>
          <ul className="auth-resource-list">
            {KAB_RESOURCES.map((item) => (
              <li key={item.href + item.title}>
                <a href={item.href} target="_blank" rel="noreferrer">
                  <strong>{item.title}</strong>
                  <span>{item.note}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>

        <p className="auth-showcase-foot">
          Visit{' '}
          <a href="https://www.kab.ac.ug/" target="_blank" rel="noreferrer">
            kab.ac.ug
          </a>{' '}
          or return to the <Link to="/">KabQue home</Link>.
        </p>
      </div>
    </aside>
  );
}
