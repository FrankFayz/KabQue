export default function SecretCodeCard({ code, scheduledDate }) {
  if (!code) {
    return (
      <div className="student-wait-note">
        <p className="label">Secret code</p>
        <p>
          Waiting for the next supervisor schedule. KabQue will email/SMS your
          queue number and secret code when your batch is notified — you cannot
          set that date yourself.
        </p>
      </div>
    );
  }

  return (
    <div className="secret-box">
      <span className="label">Your secret code</span>
      <p className="code">{code}</p>
      <p className="muted">
        Show this code at the desk on {scheduledDate || 'your scheduled day'}. Do
        not share it.
      </p>
    </div>
  );
}
