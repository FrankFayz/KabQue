import { Link } from 'react-router-dom';

export default function Brand() {
  return (
    <Link to="/" className="brand" aria-label="KabQue — Kabale University">
      <img
        className="brand-badge"
        src="/kabale-badge.png"
        alt=""
        width={46}
        height={46}
      />
      <span className="brand-text">
        <span className="brand-name">KabQue</span>
        <span className="brand-sub">Kabale University</span>
      </span>
    </Link>
  );
}
