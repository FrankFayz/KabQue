export default function SecretCodeCard({ code, scheduledDate }) {
  if (!code) {
    return (
      <p className="muted block-note">
        You are in the priority queue. When your day is set, KabQue will send an
        email/SMS with your secret code.
      </p>
    );
  }

  return (
    <div className="secret-box">
      <span className="label">Your secret code</span>
      <p className="code">{code}</p>
      <p className="muted">
        Show this code to the admin on {scheduledDate}. Do not share it.
      </p>
    </div>
  );
}
