const CAMPUS_SHOTS = [
  {
    src: '/kabale-tour-leisure.jpg',
    alt: 'Kabale University students travelling for a university tour and leisure trip',
    label: 'Tour & leisure',
    span: 'tall',
  },
  {
    src: '/kabale-spark-hub-c.jpg',
    alt: 'Official guests at the MTN Spark Hub launch, Kabale University',
    label: 'Innovation launch',
    span: 'wide',
  },
  {
    src: '/kabale-spark-hub-building.jpg',
    alt: 'Kabale MTN Spark Hub building exterior at Kikungiri Campus',
    label: 'Spark Hub building',
    span: 'normal',
  },
  {
    src: '/kabale-chancellor-installation.jpg',
    alt: 'Installation of Kabale University chancellor at the main campus',
    label: 'Academic life',
    span: 'normal',
  },
  {
    src: '/kabale-sports.jpg',
    alt: 'Kabale University football match from the campus sports gallery',
    label: 'Sports',
    span: 'wide',
  },
  {
    src: '/kabale-teaching-facility.jpg',
    alt: 'Teaching facilities at Kabale University',
    label: 'Teaching facilities',
    span: 'normal',
  },
];

/**
 * University-style campus imagery — every photo unique across the home page.
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
            From the MTN Spark Hub to open grounds — the home of ordered fresher
            intake for Kabale University.
          </p>
        </header>

        <div className="campus-mosaic" role="list">
          {CAMPUS_SHOTS.map((shot) => (
            <figure
              key={shot.src}
              className={`campus-tile campus-tile-${shot.span}`}
              role="listitem"
            >
              <img
                src={shot.src}
                alt={shot.alt}
                loading="lazy"
                decoding="async"
                width={1600}
                height={1067}
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
