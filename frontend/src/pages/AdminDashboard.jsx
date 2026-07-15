import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, getStoredUser } from '../api';
import { isMainAdmin } from '../authRoles';
import AdminStats from '../components/admin/AdminStats';
import AnalyticsBreakdown from '../components/admin/AnalyticsBreakdown';
import BatchResultTable from '../components/admin/BatchResultTable';
import NotifyBatchForm from '../components/admin/NotifyBatchForm';
import QueueTable from '../components/admin/QueueTable';
import VerifyCodePanel from '../components/admin/VerifyCodePanel';
import Alert from '../components/ui/Alert';

export default function AdminDashboard() {
  const viewingAsMainAdmin = isMainAdmin(getStoredUser());
  const [dash, setDash] = useState(null);
  const [queue, setQueue] = useState([]);
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [batchSize, setBatchSize] = useState(20);
  const [scheduledDate, setScheduledDate] = useState('');
  const [channel, setChannel] = useState('both');
  const [secretCode, setSecretCode] = useState('');
  const [verified, setVerified] = useState(null);
  const [notifyResult, setNotifyResult] = useState(null);
  const [pageError, setPageError] = useState('');
  const [notifyError, setNotifyError] = useState('');
  const [notifyMessage, setNotifyMessage] = useState('');
  const [verifyError, setVerifyError] = useState('');
  const [verifyMessage, setVerifyMessage] = useState('');
  const [queueError, setQueueError] = useState('');
  const [queueMessage, setQueueMessage] = useState('');
  const [notifyBusy, setNotifyBusy] = useState(false);
  const [verifyBusy, setVerifyBusy] = useState(false);
  const [queueBusy, setQueueBusy] = useState(false);
  const [rescheduleBusy, setRescheduleBusy] = useState(false);
  const [rescheduleError, setRescheduleError] = useState('');
  const [rescheduleMessage, setRescheduleMessage] = useState('');
  const [lastSynced, setLastSynced] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState('');
  const loadSeq = useRef(0);
  const statusRef = useRef(status);
  const searchRef = useRef(search);
  const notifyResultRef = useRef(notifyResult);
  statusRef.current = status;
  searchRef.current = search;
  notifyResultRef.current = notifyResult;

  const waitingCount = dash?.counts?.remaining ?? dash?.counts?.waiting ?? 0;
  const leftoversCount = dash?.counts?.batch_leftovers ?? 0;
  const schedulePool = waitingCount + leftoversCount;
  const liveBatchOpen = Boolean(notifyResult?.batch && (notifyResult?.students?.length ?? 0) >= 0);

  const loadBatch = useCallback(async (batchId) => {
    try {
      const qs = batchId
        ? `?batch_id=${batchId}&_=${Date.now()}`
        : `?_=${Date.now()}`;
      const data = await api(`/admin/batch/active/${qs}`);
      if (!data?.batch) return;
      if (Array.isArray(data.students) && data.students.length > 0) {
        setNotifyResult(data);
        return;
      }
      setNotifyResult((prev) => {
        if (prev?.batch?.id && data.batch?.id && prev.batch.id !== data.batch.id) {
          return prev;
        }
        return {
          ...data,
          message:
            data.message ||
            'No students remain in this batch (approved students leave the table).',
        };
      });
    } catch {
      // Desk still works without the batch table panel
    }
  }, []);

  const load = useCallback(async ({ manual = false } = {}) => {
    const seq = ++loadSeq.current;
    if (manual) {
      setRefreshing(true);
      setRefreshNote('');
      setPageError('');
    }

    try {
      const params = new URLSearchParams();
      const statusFilter = statusRef.current;
      const searchFilter = searchRef.current;
      if (statusFilter) params.set('status', statusFilter);
      if (searchFilter) params.set('search', searchFilter);
      params.set('_', String(Date.now()));

      const [d, q] = await Promise.all([
        api(`/admin/dashboard/?${params.toString()}`),
        api(`/admin/queue/?${params.toString()}`),
      ]);

      if (seq !== loadSeq.current) return;

      setDash(d);
      setQueue(Array.isArray(q) ? q : []);
      setLastSynced(new Date());
      setScheduledDate((prev) => {
        if (prev) return prev;
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        return tomorrow.toISOString().slice(0, 10);
      });
      setBatchSize((prev) => {
        if (prev) return prev;
        return d?.campus?.default_daily_batch_size || 20;
      });
      setPageError('');
      if (manual) {
        const waiting = d?.counts?.waiting ?? d?.counts?.remaining ?? 0;
        const total = d?.counts?.total ?? (Array.isArray(q) ? q.length : 0);
        setRefreshNote(`Updated · ${total} in queue · ${waiting} waiting`);
      }

      const batchId = notifyResultRef.current?.batch?.id;
      await loadBatch(batchId || undefined);
    } catch (err) {
      if (seq !== loadSeq.current) return;
      setPageError(err.message || 'Could not refresh desk data.');
      if (manual) setRefreshNote('');
    } finally {
      if (manual && seq === loadSeq.current) {
        setRefreshing(false);
      }
    }
  }, [loadBatch]);

  useEffect(() => {
    load({ manual: false });
  }, [status, search, load]);

  useEffect(() => {
    const id = setInterval(() => load({ manual: false }), 10000);
    return () => clearInterval(id);
  }, [load]);

  async function notifyBatch(e) {
    e.preventDefault();
    setNotifyBusy(true);
    setNotifyError('');
    setNotifyMessage('');
    try {
      const data = await api('/admin/notify/', {
        method: 'POST',
        body: {
          batch_size: Number(batchSize),
          scheduled_date: scheduledDate,
          channel,
        },
      });
      setNotifyResult(data);
      if (data.sms_failed) {
        setNotifyMessage(
          `Batch sent. Emails ${data.emails_sent ?? 0}, SMS failed ${data.sms_failed}.`
        );
      } else {
        setNotifyMessage(
          `Batch sent. Notified ${data.notified_count}, emails ${data.emails_sent ?? 0}, SMS ${data.sms_sent ?? 0}.`
        );
      }
      if (data.shortage) {
        setNotifyError(
          `Only ${data.available} waiting (you asked for ${data.requested}); all remaining were notified.`
        );
      }
      await load({ manual: false });
    } catch (err) {
      setNotifyError(err.message || 'Could not send notifications.');
    } finally {
      setNotifyBusy(false);
    }
  }

  async function verifyCode(e) {
    e.preventDefault();
    setVerifyBusy(true);
    setVerifyError('');
    setVerifyMessage('');
    setVerified(null);
    try {
      const data = await api('/admin/verify-code/', {
        method: 'POST',
        body: { secret_code: secretCode.trim().toUpperCase() },
      });
      setVerified(data);
      setVerifyMessage(data.message || 'Identity confirmed.');
      if (data.counts) {
        setDash((prev) => (prev ? { ...prev, counts: data.counts } : { counts: data.counts }));
      }
      await load({ manual: false });
    } catch (err) {
      const detail =
        err?.data?.detail ||
        err.message ||
        'Invalid or already-used secret code.';
      setVerifyError(String(detail));
      setVerified(null);
      setVerifyMessage('');
    } finally {
      setVerifyBusy(false);
    }
  }

  async function complete(decision) {
    if (!verified?.entry?.id) return;
    setVerifyBusy(true);
    setVerifyError('');
    try {
      const data = await api('/admin/complete-verification/', {
        method: 'POST',
        body: {
          queue_entry_id: verified.entry.id,
          decision,
          notes: '',
        },
      });
      setVerifyMessage(data.message || `Marked as ${decision}.`);
      if (data.counts) {
        setDash((prev) => (prev ? { ...prev, counts: data.counts } : { counts: data.counts }));
      }
      if (data.batch) {
        setNotifyResult(data.batch);
      } else if (data.removed_queue_entry_id) {
        setNotifyResult((prev) => {
          if (!prev?.students?.length) return prev;
          const nextStudents = prev.students.filter(
            (s) => s.queue_entry_id !== data.removed_queue_entry_id
          );
          return {
            ...prev,
            students: nextStudents,
            notified_count: nextStudents.length,
            remaining_in_batch: nextStudents.length,
            message:
              decision === 'approved' || decision === 'rejected'
                ? `Student ${decision}. Removed from batch table — ${nextStudents.length} remain for end-of-day reschedule.`
                : prev.message,
          };
        });
      }
      setVerified(null);
      setSecretCode('');
      await load({ manual: false });
    } catch (err) {
      setVerifyError(err.message || 'Could not complete verification.');
    } finally {
      setVerifyBusy(false);
    }
  }

  async function rescheduleEntry(queueEntryId, nextDate) {
    setQueueBusy(true);
    setQueueError('');
    setQueueMessage('');
    try {
      const data = await api('/admin/reschedule/', {
        method: 'POST',
        body: {
          queue_entry_id: queueEntryId,
          scheduled_date: nextDate,
        },
      });
      setQueueMessage(data.message || 'Rescheduled.');
      await load({ manual: false });
    } catch (err) {
      setQueueError(err.message);
    } finally {
      setQueueBusy(false);
    }
  }

  async function batchReschedule({ batchId, count, scheduledDate: nextDate }) {
    setRescheduleBusy(true);
    setRescheduleError('');
    setRescheduleMessage('');
    try {
      const data = await api('/admin/batch-reschedule/', {
        method: 'POST',
        body: {
          batch_id: batchId,
          count: Number(count),
          scheduled_date: nextDate,
          channel,
        },
      });
      setNotifyResult(data);
      setRescheduleMessage(data.message || 'Batch rescheduled.');
      await load({ manual: false });
      return true;
    } catch (err) {
      setRescheduleError(err.message || 'Could not reschedule this batch.');
      return false;
    } finally {
      setRescheduleBusy(false);
    }
  }

  const stageHint =
    schedulePool > 0
      ? `${schedulePool} ready to notify · waiting joiners appear on the Live queue as “Queued” until you send a batch`
      : liveBatchOpen
        ? 'Verify students with their secret code, then approve or reject'
        : 'Waiting for freshers to join on campus';

  return (
    <section className="dash desk-dash">
      <header className="desk-welcome">
        <div className="desk-welcome-copy">
          <p className="desk-welcome-kicker">
            {viewingAsMainAdmin ? 'Main Admin · desk monitor' : 'Supervisor desk'}
          </p>
          <h1>KabQue control</h1>
          <p className="desk-welcome-lede">{stageHint}</p>
        </div>
        <div className="desk-welcome-actions">
          {viewingAsMainAdmin ? (
            <Link to="/main-admin" className="btn btn-secondary">
              Back to Main Admin
            </Link>
          ) : null}
          {lastSynced ? (
            <span className="dash-refreshed">
              {refreshing ? 'Refreshing…' : `Live · ${lastSynced.toLocaleTimeString()}`}
            </span>
          ) : null}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => load({ manual: true })}
            disabled={refreshing}
            aria-busy={refreshing}
          >
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      <ol className="desk-flow" aria-label="Desk workflow">
        <li className={schedulePool > 0 ? 'is-active' : ''}>
          <span className="desk-flow-n">1</span>
          <span className="desk-flow-copy">
            <strong>Waiting</strong>
            <em>{waitingCount} joiner{waitingCount === 1 ? '' : 's'}</em>
          </span>
        </li>
        <li className={schedulePool > 0 ? 'is-active' : ''}>
          <span className="desk-flow-n">2</span>
          <span className="desk-flow-copy">
            <strong>Notify batch</strong>
            <em>Assign day + codes</em>
          </span>
        </li>
        <li>
          <span className="desk-flow-n">3</span>
          <span className="desk-flow-copy">
            <strong>Verify</strong>
            <em>Secret code at desk</em>
          </span>
        </li>
        <li>
          <span className="desk-flow-n">4</span>
          <span className="desk-flow-copy">
            <strong>Complete</strong>
            <em>Approve or reject</em>
          </span>
        </li>
      </ol>

      <Alert>{pageError}</Alert>
      <Alert>{queueError}</Alert>
      <Alert variant="info">
        {!queueError ? queueMessage || refreshNote : ''}
      </Alert>

      <AdminStats counts={dash?.counts} />
      <AnalyticsBreakdown
        byFaculty={dash?.by_faculty}
        byProgramme={dash?.by_programme}
        totalInQueue={dash?.counts?.total ?? 0}
      />

      <div className="admin-grid">
        <NotifyBatchForm
          batchSize={batchSize}
          scheduledDate={scheduledDate}
          channel={channel}
          busy={notifyBusy}
          remaining={waitingCount}
          leftovers={leftoversCount}
          error={notifyError}
          message={notifyMessage}
          onBatchSizeChange={setBatchSize}
          onScheduledDateChange={setScheduledDate}
          onChannelChange={setChannel}
          onSubmit={notifyBatch}
        />
        <VerifyCodePanel
          secretCode={secretCode}
          verified={verified}
          busy={verifyBusy}
          error={verifyError}
          message={verifyMessage}
          onSecretCodeChange={(value) => {
            setSecretCode(value);
            if (verifyError) setVerifyError('');
          }}
          onVerify={verifyCode}
          onComplete={complete}
          onClear={() => {
            setVerified(null);
            setSecretCode('');
            setVerifyError('');
            setVerifyMessage('');
          }}
        />
      </div>

      <BatchResultTable
        result={notifyResult}
        onBatchReschedule={batchReschedule}
        rescheduleBusy={rescheduleBusy}
        rescheduleError={rescheduleError}
        rescheduleMessage={rescheduleMessage}
      />
      <QueueTable
        queue={queue}
        status={status}
        search={search}
        busy={queueBusy || refreshing}
        onStatusChange={setStatus}
        onSearchChange={setSearch}
        onReschedule={rescheduleEntry}
      />
    </section>
  );
}
