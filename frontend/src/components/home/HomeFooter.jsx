import { Link } from 'react-router-dom';

const KAB_LINKS = [
  { label: 'University website', href: 'https://www.kab.ac.ug/' },
  { label: 'Admissions', href: 'https://admissions.kab.ac.ug/' },
  { label: 'Academic Registrar', href: 'https://www.kab.ac.ug/university_unit/office-of-the-academic-registrar/' },
  { label: 'Contact Kabale', href: 'https://www.kab.ac.ug/connect/contact-us/' },
  { label: 'Announcements', href: 'https://www.kab.ac.ug/announcement/' },
];

const KABQUE_LINKS = [
  { label: 'Sign in', to: '/login' },
  { label: 'Create account', to: '/register' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Features', href: '#features' },
];

export default function HomeFooter() {
  return (
    <footer className="home-footer" id="contact">
      <div className="home-footer-inner">
        <div className="home-footer-brand">
          <img
            src="/kabale-badge.png"
            alt=""
            width={56}
            height={56}
            className="home-footer-badge"
          />
          <div>
            <p className="home-footer-name">KabQue</p>
            <p className="home-footer-uni">Kabale University</p>
            <p className="home-footer-motto">Knowledge is the Future</p>
          </div>
        </div>

        <div className="home-footer-cols">
          <div className="home-footer-col">
            <p className="home-footer-label">KabQue</p>
            <ul>
              {KABQUE_LINKS.map((link) => (
                <li key={link.label}>
                  {link.to ? (
                    <Link to={link.to}>{link.label}</Link>
                  ) : (
                    <a href={link.href}>{link.label}</a>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div className="home-footer-col">
            <p className="home-footer-label">Kabale University</p>
            <ul>
              {KAB_LINKS.map((link) => (
                <li key={link.label}>
                  <a href={link.href} target="_blank" rel="noopener noreferrer">
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div className="home-footer-col">
            <p className="home-footer-label">Campus</p>
            <ul className="home-footer-address">
              <li>Plot 364 Block 3, Kikungiri Hill</li>
              <li>Kabale Municipality, Uganda</li>
              <li>P.O. Box 317, Kabale</li>
              <li>
                <a href="mailto:admissions@kab.ac.ug">admissions@kab.ac.ug</a>
              </li>
              <li>
                <a href="tel:+256782860259">+256 782 860 259</a>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <div className="home-footer-bar">
        <p>© {new Date().getFullYear()} Kabale University · KabQue fresher document queue</p>
        <p>For official university notices, always check kab.ac.ug</p>
      </div>
    </footer>
  );
}
