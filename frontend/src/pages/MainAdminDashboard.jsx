import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import Alert from '../components/ui/Alert';
import PageHeader from '../components/ui/PageHeader';
import StatusPill from '../components/ui/StatusPill';

const TABS = [
  { id: 'freshers', label: 'Freshers' },
  { id: 'admins', label: 'Admins' },
  { id: 'supervisors', label: 'Supervisors' },
];

function statusLabel(status) {
  const map = {
    waiting: 'Waiting',
    notified: 'Notified',
    checked_in: 'Checked in',
    approved: 'Approved',
    rejected: 'Rejected',
    skipped: 'Skipped',
    not_in_queue: 'Not in queue',
    pending: 'Pending approval',
  };
  return map[status] || status || '—';
}

export default function MainAdminDashboard() {
  const [tab, setTab] = useState('freshers');
  const [totals, setTotals] = useState(null);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(null);

  const loadOverview = useCallback(async () => {
    const data = await api('/main-admin/overview/');
    setTotals(data.totals || null);
  }, []);

  const loadTab = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      let path = '/main-admin/freshers/';
      if (tab === 'admins') path = '/main-admin/admins/';
      if (tab === 'supervisors') path = '/main-admin/supervisors/';
      const params = new URLSearchParams();
      if (tab === 'freshers' && search.trim()) params.set('search', search.trim());
      const qs = params.toString();
      const data = await api(`${path}${qs ? `?${qs}` : ''}`);
      setRows(Array.isArray(data.results) ? data.results : []);
      setTotal(data.total ?? 0);
      await loadOverview();
    } catch (err) {
      setError(err.message);
      setRows([]);
      setTotal(0);
    } finally {
      setBusy(false);
    }
  }, [tab, search, loadOverview]);

  useEffect(() => {
    loadTab();
  }, [loadTab]);

  async function setSupervisorApproval(userId, approve) {
    setActionBusy(userId);
    setMessage('');
    setError('');
    try {
      const data = await api('/main-admin/approve-supervisor/', {
        method: 'POST',
        body: { user_id: userId, approve },
      });
      setMessage(data.message || (approve ? 'Supervisor approved.' : 'Approval revoked.'));
      await loadTab();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(null);
    }
  }

  const totalForTab =
    tab === 'freshers'
      ? totals?.freshers ?? total
      : tab === 'admins'
        ? totals?.admins ?? total
        : totals?.supervisors ?? total;

  return (
    <div className="panel-page main-admin-page">
      <PageHeader
        eyebrow="System control"
        title="Main Admin"
        action={
          <nav className="main-admin-monitor-nav" aria-label="Monitor pages">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setTab('freshers')}
            >
              Students
            </button>
            <Link to="/admin" className="btn btn-secondary">
              Supervisors
            </Link>
          </nav>
        }
      />

      <p className="main-admin-lead">
        Control all KabQue accounts. Approve Kabale staff supervisors before they can
        use the desk. Browse freshers and their verification status.
      </p>

      <Alert>{error}</Alert>
      {message ? <Alert variant="info">{message}</Alert> : null}

      <div className="stat-row main-admin-stats">
        <button
          type="button"
          className={`stat${tab === 'freshers' ? ' stat-active' : ''}`}
          onClick={() => setTab('freshers')}
        >
          <span className="label">Freshers</span>
          <strong>{totals?.freshers ?? 0}</strong>
          <span className="stat-hint">Registered students</span>
        </button>
        <button
          type="button"
          className={`stat${tab === 'admins' ? ' stat-active' : ''}`}
          onClick={() => setTab('admins')}
        >
          <span className="label">Admins</span>
          <strong>{totals?.admins ?? 0}</strong>
          <span className="stat-hint">Main Admin accounts</span>
        </button>
        <button
          type="button"
          className={`stat${tab === 'supervisors' ? ' stat-active' : ''}`}
          onClick={() => setTab('supervisors')}
        >
          <span className="label">Supervisors</span>
          <strong>{totals?.supervisors ?? 0}</strong>
          <span className="stat-hint">
            {totals?.supervisors_pending
              ? `${totals.supervisors_pending} pending approval`
              : 'Kabale staff desk'}
          </span>
        </button>
      </div>

      <div className="panel queue-browser main-admin-panel">
        <div className="main-admin-tabs" role="tablist" aria-label="Directory">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              className={`main-admin-tab${tab === t.id ? ' is-active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="table-tools">
          <div>
            <h2>
              {tab === 'freshers' && 'All freshers'}
              {tab === 'admins' && 'All admins'}
              {tab === 'supervisors' && 'All supervisors'}
            </h2>
            <p className="main-admin-count">
              Total: <strong>{totalForTab}</strong>
              {busy ? ' · Loading…' : ''}
            </p>
          </div>
          {tab === 'freshers' ? (
            <label className="main-admin-search">
              Search
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Reg no, name, faculty…"
              />
            </label>
          ) : null}
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              {tab === 'freshers' ? (
                <tr>
                  <th>Registration</th>
                  <th>Name</th>
                  <th>Faculty</th>
                  <th>Programme</th>
                  <th>Contact</th>
                  <th>Verification</th>
                </tr>
              ) : tab === 'admins' ? (
                <tr>
                  <th>Username</th>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Joined</th>
                </tr>
              ) : (
                <tr>
                  <th>Email</th>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Joined</th>
                  <th>Action</th>
                </tr>
              )}
            </thead>
            <tbody>
              {!rows.length && !busy ? (
                <tr>
                  <td colSpan={tab === 'freshers' ? 6 : tab === 'admins' ? 4 : 5}>
                    No records found.
                  </td>
                </tr>
              ) : null}
              {tab === 'freshers' &&
                rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <strong>{row.registration_number}</strong>
                    </td>
                    <td>{row.full_name || '—'}</td>
                    <td>{row.faculty || '—'}</td>
                    <td>{row.programme || '—'}</td>
                    <td>
                      <div className="main-admin-contact">
                        <span>{row.email || '—'}</span>
                        <span>{row.phone || ''}</span>
                      </div>
                    </td>
                    <td>
                      <StatusPill status={row.verification_status}>
                        {statusLabel(row.verification_status)}
                      </StatusPill>
                      {row.queue_position ? (
                        <span className="main-admin-pos">#{row.queue_position}</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              {tab === 'admins' &&
                rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <code className="main-admin-username">{row.username}</code>
                    </td>
                    <td>{row.full_name || '—'}</td>
                    <td>Main Admin</td>
                    <td>
                      {row.date_joined
                        ? new Date(row.date_joined).toLocaleDateString()
                        : '—'}
                    </td>
                  </tr>
                ))}
              {tab === 'supervisors' &&
                rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.email || row.username}</td>
                    <td>{row.full_name || '—'}</td>
                    <td>
                      <StatusPill status={row.is_approved ? 'approved' : 'pending'}>
                        {row.is_approved ? 'Approved' : 'Pending approval'}
                      </StatusPill>
                    </td>
                    <td>
                      {row.date_joined
                        ? new Date(row.date_joined).toLocaleDateString()
                        : '—'}
                    </td>
                    <td>
                      {row.is_approved ? (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={actionBusy === row.id}
                          onClick={() => setSupervisorApproval(row.id, false)}
                        >
                          Revoke
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          disabled={actionBusy === row.id}
                          onClick={() => setSupervisorApproval(row.id, true)}
                        >
                          Approve
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
