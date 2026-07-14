export default function SecretCodeCard({ code, scheduledDate }) {
  if (!code) {
    return (
      <p className="muted block-note">
        You are waiting for the next supervisor schedule. KabQue will send an
        email/SMS with your queue number and secret code when your batch is
        notified — you cannot set that date yourself.
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
