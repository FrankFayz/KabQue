import { Link } from 'react-router-dom';

const QUEUE_SLOTS = ['1', '2', '3', '4', 'YOU'];

export default function Hero() {
  return (
    <section className="cover">
      <div className="cover-media" aria-hidden="true">
        <img
          src="/kabale-campus-building.png"
          alt=""
          className="cover-photo"
        />
        <div className="cover-veil" />
      </div>

      <div className="cover-frame">
        <aside className="cover-stage" aria-label="KabQue priority queue">
          <div className="cover-stage-inner">
            <img
              className="cover-stage-badge"
              src="/kabale-badge.png"
              alt="Kabale University badge"
              width={200}
              height={200}
            />

            <div className="cover-queue-rail" role="list" aria-label="Queue order">
              {QUEUE_SLOTS.map((slot) => (
                <div
                  key={slot}
                  role="listitem"
                  className={`cover-queue-slot${slot === 'YOU' ? ' is-you' : ''}`}
                >
                  {slot}
                </div>
              ))}
            </div>
          </div>
        </aside>

        <div className="cover-copy">
          <p className="cover-uni">Kabale University</p>
          <h1 className="cover-brand">KabQue</h1>
          <span className="cover-rule" aria-hidden="true" />

          <p className="cover-lede">
            A fair campus queue for fresher document approval. Sign in when you are ready.
          </p>

          <div className="cover-cta">
            <Link to="/register" className="btn btn-header-create">
              Create account
            </Link>
            <Link to="/login" className="btn btn-cover-secondary">
              Sign in
            </Link>
          </div>

          <div className="cover-foot">
            <p className="cover-motto">Knowledge is the Future</p>
            <p className="cover-meta">Kikungiri Campus · Freshers intake</p>
          </div>
        </div>
      </div>
    </section>
  );
}
