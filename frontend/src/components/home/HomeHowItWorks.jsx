const STEPS = [
  {
    n: '01',
    title: 'Create your account',
    text: 'Sign up with your registration number, then complete your name, faculty, programme, and contact details.',
  },
  {
    n: '02',
    title: 'Join on campus',
    text: 'When you are at Kikungiri Campus, open KabQue and join the queue. GPS confirms you are in the allowed zone.',
  },
  {
    n: '03',
    title: 'Wait for your day',
    text: 'Supervisors notify your batch in arrival order. If you cannot attend that day, return to waiting and wait for the next schedule — you do not pick a priority date.',
  },
  {
    n: '04',
    title: 'Verify at the desk',
    text: 'Present your secret code at the approval desk. Staff confirm your identity and process your documents.',
  },
];

export default function HomeHowItWorks() {
  return (
    <section className="home-section home-how" id="how-it-works" aria-labelledby="how-heading">
      <div className="home-section-inner">
        <header className="home-section-head">
          <p className="home-kicker">Process</p>
          <h2 id="how-heading">How KabQue works</h2>
          <p className="home-lede">
            Four clear steps from signup to desk verification — built for Kabale
            University freshers at Kikungiri Campus.
          </p>
        </header>

        <div className="how-layout">
          <ol className="how-steps">
            {STEPS.map((step) => (
              <li key={step.n} className="how-step">
                <span className="how-step-n" aria-hidden="true">
                  {step.n}
                </span>
                <div className="how-step-copy">
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </div>
              </li>
            ))}
          </ol>

          <figure className="how-visual">
            <img
              src="/kabale-spark-hub-a.jpg"
              alt="MTN Spark Hub computer lab at Kabale University"
              width={1600}
              height={1067}
              loading="lazy"
              decoding="async"
            />
            <figcaption>Kikungiri Campus · MTN Spark Hub · ordered intake, one student at a time</figcaption>
          </figure>
        </div>
      </div>
    </section>
  );
}
