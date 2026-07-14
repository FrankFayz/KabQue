const FEATURES = [
  {
    title: 'Fair arrival order',
    text: 'Waiting students are notified in first-come order. Queue numbers 1–N are assigned only when your day batch is called — not when you join.',
    image: '/kabale-campus-building.png',
    alt: 'Kabale University campus building',
    tone: 'blue',
  },
  {
    title: 'Email and SMS alerts',
    text: 'Your secret code and approval day are delivered to the contacts you saved. Stay off the corridor queues until KabQue calls you.',
    image: '/brochure-img-1-73.png',
    alt: 'Students and campus life at Kabale University',
    tone: 'green',
  },
  {
    title: 'Desk-ready verification',
    text: 'Supervisors confirm identity with your secret code, then approve, reject, or reschedule. The live desk stays accurate for staff and freshers.',
    image: '/brochure-img-1-75.png',
    alt: 'Kabale University academic community',
    tone: 'ink',
  },
];

export default function HomeFeatures() {
  return (
    <section className="home-section home-features" id="features" aria-labelledby="features-heading">
      <div className="home-section-inner">
        <header className="home-section-head home-section-head-center">
          <p className="home-kicker">Why KabQue</p>
          <h2 id="features-heading">Built for a calm fresher intake</h2>
          <p className="home-lede">
            Fewer crowds at the door. Clear communication. A desk that knows who is next.
          </p>
        </header>

        <div className="feature-list">
          {FEATURES.map((feature, index) => (
            <article
              key={feature.title}
              className={`feature-row${index % 2 === 1 ? ' is-flip' : ''} tone-${feature.tone}`}
            >
              <div className="feature-copy">
                <p className="feature-index" aria-hidden="true">
                  {String(index + 1).padStart(2, '0')}
                </p>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
              </div>
              <figure className="feature-media">
                <img
                  src={feature.image}
                  alt={feature.alt}
                  width={800}
                  height={560}
                  loading="lazy"
                />
              </figure>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
