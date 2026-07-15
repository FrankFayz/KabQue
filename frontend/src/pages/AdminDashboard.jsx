import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import AdminStats from '../components/admin/AdminStats';
import AnalyticsBreakdown from '../components/admin/AnalyticsBreakdown';
import BatchResultTable from '../components/admin/BatchResultTable';
import NotifyBatchForm from '../components/admin/NotifyBatchForm';
import QueueTable from '../components/admin/QueueTable';
import VerifyCodePanel from '../components/admin/VerifyCodePanel';
import Alert from '../components/ui/Alert';

export default function AdminDashboard() {
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
  const [showBreakdown, setShowBreakdown] = useState(false);
  const [searchApplied, setSearchApplied] = useState('');
  const loadSeq = useRef(0);
  const statusRef = useRef(status);
  const searchRef = useRef(searchApplied);
  const notifyResultRef = useRef(notifyResult);
  const batchZoneRef = useRef(null);
  statusRef.current = status;
  searchRef.current = searchApplied;
  notifyResultRef.current = notifyResult;

  const waitingCount = dash?.counts?.remaining ?? dash?.counts?.waiting ?? 0;
  const leftoversCount = dash?.counts?.batch_leftovers ?? 0;
  const schedulePool = waitingCount + leftoversCount;
  const liveBatchOpen = Boolean(
    notifyResult?.batch?.id || (notifyResult?.students || []).length > 0
  );

  useEffect(() => {
    const id = setTimeout(() => setSearchApplied(search.trim()), 350);
    return () => clearTimeout(id);
  }, [search]);

  const applyBatchPayload = useCallback((data) => {
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
  }, []);

  const load = useCallback(async ({ manual = false } = {}) => {
    const seq = ++loadSeq.current;
    if (manual) {
      setRefreshing(true);
      setRefreshNote('');
      setPageError('');
    }

    try {
      const stamp = String(Date.now());
      const queueParams = new URLSearchParams();
      const statusFilter = statusRef.current;
      const searchFilter = searchRef.current;
      if (statusFilter) queueParams.set('status', statusFilter);
      if (searchFilter) queueParams.set('search', searchFilter);
      queueParams.set('_', stamp);

      const batchId = notifyResultRef.current?.batch?.id;
      const batchQs = batchId
        ? `?batch_id=${batchId}&_=${stamp}`
        : `?_=${stamp}`;

      const [d, q, batchData] = await Promise.all([
        api(`/admin/dashboard/?_=${stamp}`),
        api(`/admin/queue/?${queueParams.toString()}`),
        api(`/admin/batch/active/${batchQs}`).catch(() => null),
      ]);

      if (seq !== loadSeq.current) return;

      setDash(d);
      setQueue(Array.isArray(q) ? q : []);
      if (batchData) applyBatchPayload(batchData);
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
    } catch (err) {
      if (seq !== loadSeq.current) return;
      setPageError(err.message || 'Could not refresh desk data.');
      if (manual) setRefreshNote('');
    } finally {
      if (manual && seq === loadSeq.current) {
        setRefreshing(false);
      }
    }
  }, [applyBatchPayload]);

  useEffect(() => {
    load({ manual: false });
  }, [status, searchApplied, load]);

  useEffect(() => {
    const tick = () => {
      if (document.hidden) return;
      load({ manual: false });
    };
    const id = setInterval(tick, 30000);
    const onVis = () => {
      if (!document.hidden) load({ manual: false });
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
    };
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
        const reason = Array.isArray(data.sms_errors) && data.sms_errors.length
          ? ` Reason: ${data.sms_errors[0]}`
          : !data.sms_configured
            ? ' SMS is not set up on the server yet.'
            : ' Open MySMSGate on the gateway phone and keep it online.';
        setNotifyMessage(
          `Batch sent. Emails: ${data.emails_sent ?? 0}. SMS failed for ${data.sms_failed} student(s).${reason}`
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
      requestAnimationFrame(() => {
        batchZoneRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
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
      setVerifyError(err.message || 'Invalid or already-used secret code.');
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
          const remainNote =
            decision === 'back_to_queue'
              ? `Returned to waiting nearer the front — ${nextStudents.length} remain in today’s batch.`
              : `Student ${decision}. Removed from batch table — ${nextStudents.length} remain.`;
          return {
            ...prev,
            students: nextStudents,
            notified_count: nextStudents.length,
            remaining_in_batch: nextStudents.length,
            message: remainNote,
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
      ? `${schedulePool} ready to schedule`
      : liveBatchOpen
        ? 'Batch open · verify codes'
        : 'Waiting for campus joiners';

  return (
    <section className="dash desk-dash">
      <header className="desk-welcome">
        <div className="desk-welcome-copy">
          <p className="desk-welcome-kicker">Kabale University · Supervisor</p>
          <h1>Desk control</h1>
          <p className="desk-welcome-lede">{stageHint}</p>
        </div>
        <div className="desk-welcome-actions">
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

      <Alert>{pageError}</Alert>
      <Alert>{queueError}</Alert>
      <Alert variant="info">
        {!queueError ? queueMessage || refreshNote : ''}
      </Alert>

      <AdminStats counts={dash?.counts} />

      <section className="desk-zone" aria-labelledby="desk-ops-heading">
        <header className="desk-zone-head">
          <div>
            <p className="desk-zone-kicker">Desk operations</p>
            <h2 id="desk-ops-heading">Schedule & verify</h2>
          </div>
        </header>
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
          />
        </div>
      </section>

      <section
        className="desk-zone"
        aria-labelledby="desk-batch-heading"
        ref={batchZoneRef}
      >
        <header className="desk-zone-head">
          <div>
            <p className="desk-zone-kicker">Today’s list</p>
            <h2 id="desk-batch-heading">Batch result table</h2>
          </div>
        </header>
        <BatchResultTable
          result={notifyResult}
          onBatchReschedule={batchReschedule}
          rescheduleBusy={rescheduleBusy}
          rescheduleError={rescheduleError}
          rescheduleMessage={rescheduleMessage}
        />
      </section>

      <section className="desk-zone" aria-labelledby="desk-queue-heading">
        <header className="desk-zone-head">
          <div>
            <p className="desk-zone-kicker">Lookup</p>
            <h2 id="desk-queue-heading">Live queue</h2>
          </div>
        </header>
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

      <section className="desk-zone desk-zone-insight" aria-labelledby="desk-insight-heading">
        <header className="desk-zone-head desk-zone-head-insight">
          <div>
            <p className="desk-zone-kicker">Insights</p>
            <h2 id="desk-insight-heading">Faculty & programme breakdown</h2>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setShowBreakdown((v) => !v)}
            aria-expanded={showBreakdown}
          >
            {showBreakdown ? 'Hide breakdown' : 'Show breakdown'}
          </button>
        </header>
        {showBreakdown ? (
          <AnalyticsBreakdown
            byFaculty={dash?.by_faculty}
            byProgramme={dash?.by_programme}
            totalInQueue={dash?.counts?.total ?? 0}
          />
        ) : (
          <p className="desk-zone-lede desk-zone-lede-muted">
            Optional overview of who is in the live queue by faculty and
            programme. Open when you need reporting — not during desk rush.
          </p>
        )}
      </section>
    </section>
  );
}
