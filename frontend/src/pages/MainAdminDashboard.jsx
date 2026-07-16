import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import Alert from '../components/ui/Alert';
import StatusPill from '../components/ui/StatusPill';

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
    email_unverified: 'Email not verified',
  };
  return map[status] || status || '—';
}

function AccountActions({ row, busy, onLock, onDelete, extra }) {
  const locked = Boolean(row.is_locked);
  if (row.is_self) {
    return (
      <div className="main-admin-actions">
        <span className="main-admin-you" title="This is your signed-in account">
          You
        </span>
      </div>
    );
  }
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
        {busy ? 'Deleting…' : 'Delete'}
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
  const hasLoadedOnce = useRef(false);

  useEffect(() => {
    const id = setTimeout(() => setSearchApplied(search.trim()), 320);
    return () => clearTimeout(id);
  }, [search]);

  const loadTab = useCallback(
    async ({ manual = false } = {}) => {
      const seq = ++loadSeq.current;
      if (manual || !hasLoadedOnce.current) setBusy(true);
      setError('');
      if (manual) setRefreshNote('');
      try {
        let path = '/main-admin/freshers/';
        if (tab === 'admins') path = '/main-admin/admins/';
        if (tab === 'supervisors') path = '/main-admin/supervisors/';
        const params = new URLSearchParams();
        if (tab === 'freshers' && searchApplied) params.set('search', searchApplied);
        const stamp = String(Date.now());
        params.set('_', stamp);

        const [data, overview] = await Promise.all([
          api(`${path}?${params.toString()}`),
          api(`/main-admin/overview/?_=${stamp}`).catch(() => null),
        ]);
        if (seq !== loadSeq.current) return;
        setRows(Array.isArray(data.results) ? data.results : []);
        setTotal(data.total ?? 0);
        if (overview?.totals) setTotals(overview.totals);
        hasLoadedOnce.current = true;
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
    [tab, searchApplied]
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
    if (row.is_self) {
      setError('You cannot lock your own account. Ask another Main Admin.');
      return;
    }
    const label =
      row.registration_number || row.email || row.username || `user #${row.id}`;
    const isAdmin = Boolean(row.is_main_admin) || tab === 'admins';
    const ok = window.confirm(
      lock
        ? isAdmin
          ? `Lock Main Admin ${label}?\n\nThey will not be able to sign in until unlocked. At least one other Main Admin must remain able to sign in.`
          : `Lock account for ${label}?\n\nThey will not be able to sign in until unlocked.`
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
    if (row.is_self) {
      setError('You cannot delete your own account. Ask another Main Admin.');
      return;
    }
    const label =
      row.registration_number || row.email || row.username || `user #${row.id}`;
    const kind =
      tab === 'freshers'
        ? 'student'
        : tab === 'admins' || row.is_main_admin
          ? 'Main Admin'
          : 'supervisor';
    const ok = window.confirm(
      kind === 'Main Admin'
        ? `Delete Main Admin ${label} permanently?\n\nThis cannot be undone.`
        : `Delete ${kind} ${label} permanently?\n\nThis removes the account and related queue data. This cannot be undone.`
    );
    if (!ok) return;

    const deletedId = row.id;
    const snapshot = rows;
    const snapshotTotal = total;
    const snapshotTotals = totals;

    // Remove from the table immediately — do not wait for a full refetch.
    setRows((prev) => prev.filter((r) => r.id !== deletedId));
    setTotal((n) => Math.max(0, (n || 0) - 1));
    setTotals((prev) => {
      if (!prev) return prev;
      const key =
        tab === 'freshers' ? 'freshers' : tab === 'admins' ? 'admins' : 'supervisors';
      return { ...prev, [key]: Math.max(0, (prev[key] || 0) - 1) };
    });
    setActionBusy(deletedId);
    setMessage('');
    setError('');

    try {
      const data = await api('/main-admin/delete-user/', {
        method: 'POST',
        body: { user_id: deletedId },
      });
      const counts = data.counts || {};
      const countHint =
        kind === 'student' && counts.total != null
          ? ` Desk now: In queue ${counts.in_queue ?? counts.total ?? 0}, Scheduled ${counts.scheduled ?? 0}, Approved (all-time) ${counts.approved ?? 0}.`
          : '';
      setMessage((data.message || 'Account permanently deleted.') + countHint);
      // Soft refresh totals/overview in the background — row already gone.
      loadTab({ manual: false }).catch(() => {});
    } catch (err) {
      setRows(snapshot);
      setTotal(snapshotTotal);
      setTotals(snapshotTotals);
      setError(err.message || 'Could not delete this account. Try again.');
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
    tab === 'freshers' ? 8 : tab === 'admins' ? 6 : 5;

  return (
    <div className="panel-page main-admin-page kabque-ops">
      <header className="desk-welcome main-admin-welcome">
        <div className="desk-welcome-copy">
          <p className="desk-welcome-kicker">Kabale University · Control</p>
          <h1>Main Admin</h1>
          <p className="desk-welcome-lede">
            Directory, access, and supervisor approval — one clean control surface.
          </p>
        </div>
        <div className="desk-welcome-actions">
          {lastSynced ? (
            <span className="dash-refreshed desk-live-pill">
              <span className="desk-live-dot" aria-hidden="true" />
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
      </header>

      <Alert>{error}</Alert>
      {message || refreshNote ? (
        <Alert variant="info">{message || refreshNote}</Alert>
      ) : null}

      <div className="stat-row main-admin-stats" role="tablist" aria-label="Directories">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'freshers'}
          className={`stat desk-stat${tab === 'freshers' ? ' stat-active' : ''}`}
          onClick={() => setTab('freshers')}
        >
          <span className="label">Freshers</span>
          <strong>{totals?.freshers ?? 0}</strong>
          <span className="stat-hint">Registered students</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'admins'}
          className={`stat desk-stat${tab === 'admins' ? ' stat-active' : ''}`}
          onClick={() => setTab('admins')}
        >
          <span className="label">Admins</span>
          <strong>{totals?.admins ?? 0}</strong>
          <span className="stat-hint">System operators</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'supervisors'}
          className={`stat desk-stat${tab === 'supervisors' ? ' stat-active' : ''}`}
          onClick={() => setTab('supervisors')}
        >
          <span className="label">Supervisors</span>
          <strong>{totals?.supervisors ?? 0}</strong>
          <span className="stat-hint">
            {totals?.supervisors_pending
              ? `${totals.supervisors_pending} pending approval`
              : 'Desk staff'}
          </span>
        </button>
      </div>

      <div className="panel queue-browser main-admin-panel">
        <div className="main-admin-panel-head">
          <div>
            <p className="desk-zone-kicker">Directory</p>
            <h2>
              {tab === 'freshers' && 'All freshers'}
              {tab === 'admins' && 'All admins'}
              {tab === 'supervisors' && 'All supervisors'}
            </h2>
            <p className="main-admin-count">
              <strong>{totalForTab}</strong> records
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
                  <th>Secret code</th>
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
                  <th>Actions</th>
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
                      {row.secret_code ? (
                        <code className="main-admin-code">{row.secret_code}</code>
                      ) : (
                        '—'
                      )}
                    </td>
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
                  <tr
                    key={row.id}
                    className={row.is_locked ? 'row-locked' : undefined}
                  >
                    <td>
                      <code className="main-admin-username">{row.username}</code>
                      {row.is_self ? (
                        <span className="main-admin-you-inline"> · you</span>
                      ) : null}
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
              {tab === 'supervisors' &&
                rows.map((row) => (
                  <tr key={row.id} className={row.is_locked ? 'row-locked' : undefined}>
                    <td>{row.email || row.username}</td>
                    <td>{row.full_name || '—'}</td>
                    <td>
                      <div className="main-admin-status-stack">
                        <StatusPill
                          status={
                            row.email_verified === false
                              ? 'email_unverified'
                              : row.is_approved
                                ? 'approved'
                                : 'pending'
                          }
                        >
                          {row.email_verified === false
                            ? 'Awaiting email code'
                            : row.is_approved
                              ? 'Desk approved'
                              : 'Awaiting your approval'}
                        </StatusPill>
                        {row.email_verified !== false ? (
                          <span className="main-admin-email-ok">Email verified</span>
                        ) : (
                          <span className="main-admin-email-wait">
                            Must verify @kab.ac.ug first
                          </span>
                        )}
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
                              disabled={
                                actionBusy === row.id || row.email_verified === false
                              }
                              title={
                                row.email_verified === false
                                  ? 'Supervisor must verify their Kabale email first'
                                  : 'Approve desk access'
                              }
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
