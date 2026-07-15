const CAMPUS_SHOTS = [
  {
    src: '/kabale-teaching-facility.jpg',
    alt: 'Teaching facilities at Kabale University',
    label: 'Teaching facilities',
    span: 'tall',
  },
  {
    src: '/brochure-img-1-73.png',
    alt: 'Students and community life at Kabale University',
    label: 'Campus community',
    span: 'wide',
  },
  {
    src: '/brochure-page-0.jpg',
    alt: 'Kabale University campus grounds',
    label: 'Kikungiri grounds',
    span: 'normal',
  },
  {
    src: '/brochure-img-1-75.png',
    alt: 'Academic life at Kabale University',
    label: 'Academic life',
    span: 'normal',
  },
  {
    src: '/brochure-page-1.jpg',
    alt: 'Kabale University brochure campus view',
    label: 'University life',
    span: 'wide',
  },
  {
    src: '/kabale-campus-building.png',
    alt: 'Kabale University main campus building',
    label: 'Main campus',
    span: 'normal',
  },
];

/**
 * University-style campus imagery — replaces the old feature/“Why KabQue” block.
 */
export default function HomeCampus() {
  return (
    <section
      className="home-section home-campus"
      id="campus"
      aria-labelledby="campus-heading"
    >
      <div className="home-section-inner">
        <header className="home-section-head home-section-head-center">
          <p className="home-kicker">Kabale University</p>
          <h2 id="campus-heading">Life at Kikungiri Campus</h2>
          <p className="home-lede">
            From lecture halls to open grounds — the home of ordered fresher
            intake for Kabale University.
          </p>
        </header>

        <div className="campus-mosaic" role="list">
          {CAMPUS_SHOTS.map((shot) => (
            <figure
              key={shot.src + shot.label}
              className={`campus-tile campus-tile-${shot.span}`}
              role="listitem"
            >
              <img
                src={shot.src}
                alt={shot.alt}
                loading="lazy"
                width={800}
                height={600}
              />
              <figcaption>{shot.label}</figcaption>
            </figure>
          ))}
        </div>

        <p className="campus-note">
          Official university notices live at{' '}
          <a href="https://www.kab.ac.ug/" target="_blank" rel="noopener noreferrer">
            kab.ac.ug
          </a>
          . KabQue handles your fresher document queue on campus.
        </p>
      </div>
    </section>
  );
}
