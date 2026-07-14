import { useCallback, useEffect, useRef, useState } from 'react';
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

function AccountActions({ row, busy, onLock, onDelete, extra }) {
  const locked = Boolean(row.is_locked);
  return (
    <div className="main-admin-actions">
      {extra}
      <button
        type="button"
        className={`btn btn-sm ${locked ? 'btn-primary' : 'btn-secondary'}`}
        disabled={busy}
        onClick={() => onLock(row, !locked)}
        title={locked ? 'Restore sign-in access' : 'Block sign-in access'}
      >
        {locked ? 'Unlock' : 'Lock'}
      </button>
      <button
        type="button"
        className="btn btn-sm btn-danger-outline"
        disabled={busy}
        onClick={() => onDelete(row)}
        title="Permanently delete this account and related data"
      >
        Delete
      </button>
    </div>
  );
}

export default function MainAdminDashboard() {
  const [tab, setTab] = useState('freshers');
  const [totals, setTotals] = useState(null);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [searchApplied, setSearchApplied] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(null);
  const [lastSynced, setLastSynced] = useState(null);
  const [refreshNote, setRefreshNote] = useState('');
  const loadSeq = useRef(0);

  useEffect(() => {
    const id = setTimeout(() => setSearchApplied(search.trim()), 320);
    return () => clearTimeout(id);
  }, [search]);

  const loadOverview = useCallback(async () => {
    const data = await api(`/main-admin/overview/?_=${Date.now()}`);
    setTotals(data.totals || null);
  }, []);

  const loadTab = useCallback(
    async ({ manual = false } = {}) => {
      const seq = ++loadSeq.current;
      setBusy(true);
      setError('');
      if (manual) setRefreshNote('');
      try {
        let path = '/main-admin/freshers/';
        if (tab === 'admins') path = '/main-admin/admins/';
        if (tab === 'supervisors') path = '/main-admin/supervisors/';
        const params = new URLSearchParams();
        if (tab === 'freshers' && searchApplied) params.set('search', searchApplied);
        params.set('_', String(Date.now()));
        const data = await api(`${path}?${params.toString()}`);
        if (seq !== loadSeq.current) return;
        setRows(Array.isArray(data.results) ? data.results : []);
        setTotal(data.total ?? 0);
        await loadOverview();
        if (seq !== loadSeq.current) return;
        setLastSynced(new Date());
        if (manual) {
          setRefreshNote(
            `Updated · ${data.total ?? 0} ${tab === 'freshers' ? 'freshers' : tab}`
          );
        }
      } catch (err) {
        if (seq !== loadSeq.current) return;
        setError(err.message || 'Could not refresh directory.');
        setRows([]);
        setTotal(0);
        if (manual) setRefreshNote('');
      } finally {
        if (seq === loadSeq.current) setBusy(false);
      }
    },
    [tab, searchApplied, loadOverview]
  );

  useEffect(() => {
    loadTab({ manual: false });
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
      await loadTab({ manual: false });
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(null);
    }
  }

  async function lockUser(row, lock) {
    const label =
      row.registration_number || row.email || row.username || `user #${row.id}`;
    const ok = window.confirm(
      lock
        ? `Lock account for ${label}?\n\nThey will not be able to sign in until unlocked.`
        : `Unlock account for ${label}?\n\nThey will be able to sign in again.`
    );
    if (!ok) return;

    setActionBusy(row.id);
    setMessage('');
    setError('');
    try {
      const data = await api('/main-admin/lock-user/', {
        method: 'POST',
        body: { user_id: row.id, lock },
      });
      setMessage(data.message || (lock ? 'Account locked.' : 'Account unlocked.'));
      await loadTab({ manual: false });
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(null);
    }
  }

  async function deleteUser(row) {
    const label =
      row.registration_number || row.email || row.username || `user #${row.id}`;
    const kind = tab === 'freshers' ? 'student' : 'supervisor';
    const ok = window.confirm(
      `Permanently delete ${kind} ${label}?\n\n` +
        'This removes the account and related queue data from the database. This cannot be undone.'
    );
    if (!ok) return;

    const confirmText = window.prompt(
      `Type DELETE to permanently remove ${label}:`
    );
    if (confirmText !== 'DELETE') {
      setError('Deletion cancelled — you must type DELETE to confirm.');
      return;
    }

    setActionBusy(row.id);
    setMessage('');
    setError('');
    try {
      const data = await api('/main-admin/delete-user/', {
        method: 'POST',
        body: { user_id: row.id },
      });
      setMessage(data.message || 'Account permanently deleted.');
      await loadTab({ manual: false });
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

  const colSpan =
    tab === 'freshers' ? 7 : tab === 'admins' ? 5 : 5;

  return (
    <div className="panel-page main-admin-page">
      <PageHeader
        eyebrow="System control"
        title="Main Admin"
        action={
          <div className="dash-actions">
            <nav className="main-admin-monitor-nav" aria-label="Monitor pages">
              <Link to="/admin" className="btn btn-secondary">
                Supervisors
              </Link>
            </nav>
            {lastSynced ? (
              <span className="dash-refreshed">
                {busy ? 'Refreshing…' : `Updated · ${lastSynced.toLocaleTimeString()}`}
              </span>
            ) : null}
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => loadTab({ manual: true })}
              disabled={busy}
              aria-busy={busy}
            >
              {busy ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        }
      />

      <p className="main-admin-lead">
        Control all KabQue accounts. Approve Kabale staff, lock access, or permanently
        delete students and supervisors from the system.
      </p>

      <Alert>{error}</Alert>
      {message || refreshNote ? (
        <Alert variant="info">{message || refreshNote}</Alert>
      ) : null}

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
                  <th>Verification</th>
                  <th>Access</th>
                  <th>Actions</th>
                </tr>
              ) : tab === 'admins' ? (
                <tr>
                  <th>Username</th>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Access</th>
                  <th>Joined</th>
                </tr>
              ) : (
                <tr>
                  <th>Email</th>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Access</th>
                  <th>Actions</th>
                </tr>
              )}
            </thead>
            <tbody>
              {!rows.length && !busy ? (
                <tr>
                  <td colSpan={colSpan}>No records found.</td>
                </tr>
              ) : null}
              {tab === 'freshers' &&
                rows.map((row) => (
                  <tr key={row.id} className={row.is_locked ? 'row-locked' : undefined}>
                    <td>
                      <strong>{row.registration_number}</strong>
                    </td>
                    <td>
                      <div className="main-admin-contact">
                        <span>{row.full_name || '—'}</span>
                        <span>{row.email || row.phone || ''}</span>
                      </div>
                    </td>
                    <td>{row.faculty || '—'}</td>
                    <td>{row.programme || '—'}</td>
                    <td>
                      <StatusPill status={row.verification_status}>
                        {statusLabel(row.verification_status)}
                      </StatusPill>
                      {row.verification_status !== 'waiting' &&
                      row.queue_position ? (
                        <span className="main-admin-pos">#{row.queue_position}</span>
                      ) : null}
                    </td>
                    <td>
                      <StatusPill status={row.is_locked ? 'locked' : 'active'}>
                        {row.is_locked ? 'Locked' : 'Active'}
                      </StatusPill>
                    </td>
                    <td>
                      <AccountActions
                        row={row}
                        busy={actionBusy === row.id}
                        onLock={lockUser}
                        onDelete={deleteUser}
                      />
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
                      <StatusPill status={row.is_locked ? 'locked' : 'active'}>
                        {row.is_locked ? 'Locked' : 'Active'}
                      </StatusPill>
                    </td>
                    <td>
                      {row.date_joined
                        ? new Date(row.date_joined).toLocaleDateString()
                        : '—'}
                    </td>
                  </tr>
                ))}
              {tab === 'supervisors' &&
                rows.map((row) => (
                  <tr key={row.id} className={row.is_locked ? 'row-locked' : undefined}>
                    <td>{row.email || row.username}</td>
                    <td>{row.full_name || '—'}</td>
                    <td>
                      <div className="main-admin-status-stack">
                        <StatusPill status={row.is_approved ? 'approved' : 'pending'}>
                          {row.is_approved ? 'Approved' : 'Pending approval'}
                        </StatusPill>
                      </div>
                    </td>
                    <td>
                      <StatusPill status={row.is_locked ? 'locked' : 'active'}>
                        {row.is_locked ? 'Locked' : 'Active'}
                      </StatusPill>
                    </td>
                    <td>
                      <AccountActions
                        row={row}
                        busy={actionBusy === row.id}
                        onLock={lockUser}
                        onDelete={deleteUser}
                        extra={
                          row.is_approved ? (
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
                          )
                        }
                      />
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
