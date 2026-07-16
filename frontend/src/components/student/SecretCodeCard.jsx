export default function SecretCodeCard({
  code,
  scheduledDate,
  requiredDocuments = [],
}) {
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

  const docs = Array.isArray(requiredDocuments) ? requiredDocuments.filter(Boolean) : [];

  return (
    <div className="secret-box">
      <span className="label">Your secret code</span>
      <p className="code">{code}</p>
      <p className="muted">
        Show this code at the desk on {scheduledDate || 'your scheduled day'}. Do
        not share it.
      </p>
      {docs.length ? (
        <div className="secret-docs">
          <p className="secret-docs-title">Bring these documents (originals)</p>
          <ol className="secret-docs-list">
            {docs.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}
