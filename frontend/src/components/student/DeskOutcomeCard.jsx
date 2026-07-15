import StatusPill from '../ui/StatusPill';
import Panel from '../ui/Panel';

const COPY = {
  approved: {
    title: 'Documents approved',
    lead:
      'Your fresher documents were accepted at the KabQue desk. This registration is complete — you do not need to join the queue again.',
    note:
      'Keep any confirmation you received from the supervisor. If you have questions, contact the admissions desk in person.',
  },
  rejected: {
    title: 'Visit completed — not accepted',
    lead:
      'Your desk visit is finished. Documents were not accepted on this attempt. You cannot rejoin the KabQue queue with this registration.',
    note:
      'Speak to the admissions or faculty desk directly if you need guidance on what to do next.',
  },
};

export default function DeskOutcomeCard({ profile, outcome }) {
  const key = (outcome || profile?.desk_outcome || '').toLowerCase();
  const copy = COPY[key];
  if (!copy) return null;

  const reg = profile?.registration_number || '—';
  const name = profile?.full_name || 'Student';

  return (
    <Panel title="Desk result" className="desk-outcome-card">
      <div className={`desk-outcome-hero desk-outcome-${key}`}>
        <div className="desk-outcome-hero-copy">
          <p className="desk-outcome-kicker">Final status</p>
          <h2>{copy.title}</h2>
          <p className="desk-outcome-lede">{copy.lead}</p>
        </div>
        <StatusPill status={key}>{key === 'approved' ? 'Approved' : 'Rejected'}</StatusPill>
      </div>

      <div className="desk-outcome-facts" role="list">
        <div className="desk-outcome-fact" role="listitem">
          <span className="label">Name</span>
          <strong>{name}</strong>
        </div>
        <div className="desk-outcome-fact" role="listitem">
          <span className="label">Registration no.</span>
          <strong>{reg}</strong>
        </div>
        <div className="desk-outcome-fact" role="listitem">
          <span className="label">Faculty</span>
          <strong>{profile?.faculty || '—'}</strong>
        </div>
        <div className="desk-outcome-fact" role="listitem">
          <span className="label">Programme</span>
          <strong>{profile?.programme || '—'}</strong>
        </div>
      </div>

      <p className="desk-outcome-note">{copy.note}</p>

      <div className="desk-outcome-closed" aria-live="polite">
        <span className="desk-outcome-closed-icon" aria-hidden="true">
          ✓
        </span>
        <p>Queue closed for this account — join is disabled.</p>
      </div>
    </Panel>
  );
}
