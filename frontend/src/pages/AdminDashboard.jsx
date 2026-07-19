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
  /** Which desk button is in flight: 'approved' | 'rejected' | 'back_to_queue' | null */
  const [completeBusy, setCompleteBusy] = useState(null);
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
  const deliveryPollRef = useRef(0);
  statusRef.current = status;
  searchRef.current = searchApplied;
  notifyResultRef.current = notifyResult;

  const waitingCount =
    dash?.counts?.unscheduled ??
    dash?.counts?.waiting ??
    dash?.counts?.remaining ??
    0;
  const leftoversCount = dash?.counts?.batch_leftovers ?? 0;
  const liveBatchOpen = Boolean(
    notifyResult?.batch?.id || (notifyResult?.students || []).length > 0
  );

  useEffect(() => {
    const id = setTimeout(() => setSearchApplied(search.trim()), 350);
    return () => clearTimeout(id);
  }, [search]);

  const mergeDeliveryStats = useCallback((prev, data) => {
    if (!data) return prev;
    if (!prev) return data;
    if (prev.batch?.id && data.batch?.id && prev.batch.id !== data.batch.id) {
      return data;
    }
    const students =
      Array.isArray(data.students) && data.students.length > 0
        ? data.students
        : prev.students;
    return {
      ...prev,
      ...data,
      students,
      emails_sent: data.emails_sent ?? prev.emails_sent ?? 0,
      emails_failed: data.emails_failed ?? prev.emails_failed ?? 0,
      sms_sent: data.sms_sent ?? prev.sms_sent ?? 0,
      sms_failed: data.sms_failed ?? prev.sms_failed ?? 0,
      sms_errors: data.sms_errors ?? prev.sms_errors ?? [],
      delivery_pending: Boolean(data.delivery_pending),
      remaining_in_batch:
        data.remaining_in_batch ??
        (Array.isArray(students) ? students.length : prev.remaining_in_batch),
    };
  }, []);

  const applyBatchPayload = useCallback(
    (data) => {
      if (!data?.batch) return;
      setNotifyResult((prev) => {
        if (Array.isArray(data.students) && data.students.length > 0) {
          return mergeDeliveryStats(prev, data);
        }
        // Same batch with empty students: keep rows, still refresh email/SMS totals.
        if (
          prev?.students?.length > 0 &&
          data.batch?.id &&
          prev.batch?.id === data.batch.id
        ) {
          return mergeDeliveryStats(prev, {
            ...data,
            students: prev.students,
          });
        }
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
    },
    [mergeDeliveryStats]
  );

  /** Poll until background email/SMS finish so Emails sent / SMS sent stay accurate. */
  const pollBatchDelivery = useCallback(
    async (batchId, { onTick, onDone } = {}) => {
      if (!batchId) return null;
      const token = ++deliveryPollRef.current;
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      let last = null;
      for (let i = 0; i < 50; i += 1) {
        if (token !== deliveryPollRef.current) return last;
        await sleep(i === 0 ? 700 : 1400);
        try {
          const data = await api(
            `/admin/batch/active/?batch_id=${batchId}&_=${Date.now()}`
          );
          if (token !== deliveryPollRef.current) return last;
          if (!data?.batch) continue;
          last = data;
          setNotifyResult((prev) => mergeDeliveryStats(prev, data));
          notifyResultRef.current = mergeDeliveryStats(
            notifyResultRef.current,
            data
          );
          onTick?.(data);
          if (!data.delivery_pending) {
            onDone?.(data);
            return data;
          }
        } catch {
          // Keep polling through transient network blips.
        }
      }
      onDone?.(last);
      return last;
    },
    [mergeDeliveryStats]
  );

  function deliverySummaryMessage(data, fallback) {
    if (!data) return fallback;
    const mode = data.channel || channel;
    const bits = [];
    if (mode === 'email' || mode === 'both') {
      bits.push(`Emails sent ${data.emails_sent ?? 0}`);
      if (data.emails_failed) bits.push(`email failed ${data.emails_failed}`);
    }
    if (mode === 'sms' || mode === 'both') {
      bits.push(`SMS sent ${data.sms_sent ?? 0}`);
      if (data.sms_failed) bits.push(`SMS failed ${data.sms_failed}`);
    }
    if (!bits.length) return fallback;
    return `${fallback} · ${bits.join(' · ')}`;
  }

  const load = useCallback(async ({ manual = false, lite = false } = {}) => {
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

      // Background polls skip faculty/programme analytics (faster).
      const dashUrl =
        lite && !manual
          ? `/admin/dashboard/?lite=1&_=${stamp}`
          : `/admin/dashboard/?_=${stamp}`;

      const [d, q, batchData] = await Promise.all([
        api(dashUrl),
        api(`/admin/queue/?${queueParams.toString()}`),
        api(`/admin/batch/active/${batchQs}`).catch(() => null),
      ]);

      if (seq !== loadSeq.current) return;

      setDash((prev) => {
        if (!d) return prev;
        // Lite responses omit analytics — keep previous breakdown if present.
        if (lite && !manual && prev?.by_faculty && !d.by_faculty) {
          return {
            ...prev,
            counts: d.counts ?? prev.counts,
            campus: d.campus ?? prev.campus,
          };
        }
        return d;
      });
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
        const waiting =
          d?.counts?.in_queue ??
          d?.counts?.unscheduled ??
          d?.counts?.waiting ??
          d?.counts?.remaining ??
          0;
        const total = d?.counts?.total ?? waiting;
        setRefreshNote(`Updated · ${total} in queue`);
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

  /** Soft sync — never blocks button busy state. */
  function softRefresh() {
    load({ manual: false, lite: true }).catch(() => {});
  }
  useEffect(() => {
    load({ manual: false });
  }, [status, searchApplied, load]);

  useEffect(() => {
    const tick = () => {
      if (document.hidden) return;
      load({ manual: false, lite: true });
    };
    const id = setInterval(tick, 30000);
    const onVis = () => {
      if (!document.hidden) load({ manual: false, lite: true });
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
      const mode = data.channel || channel;
      if (data.delivery_pending) {
        setNotifyMessage(
          data.message ||
            `Batch ready (${mode}) · notified ${data.notified_count}. Confirming email/SMS…`
        );
        void pollBatchDelivery(data.batch?.id, {
          onDone: (final) => {
            setNotifyMessage(
              deliverySummaryMessage(
                final,
                `Batch complete (${mode}) · notified ${final?.notified_count ?? data.notified_count}`
              )
            );
          },
        });
      } else if (data.sms_failed && (mode === 'sms' || mode === 'both')) {
        const reason = Array.isArray(data.sms_errors) && data.sms_errors.length
          ? ` Reason: ${data.sms_errors[0]}`
          : !data.sms_configured
            ? ' SMS is not set up on the server yet.'
            : ' Open MySMSGate on the gateway phone and keep it online.';
        setNotifyMessage(
          `Batch sent (${mode}). Emails: ${data.emails_sent ?? 0}. SMS failed for ${data.sms_failed} student(s).${reason}`
        );
      } else {
        setNotifyMessage(
          deliverySummaryMessage(
            data,
            `Batch sent (${mode}) · notified ${data.notified_count}`
          )
        );
      }
      if (data.shortage) {
        setNotifyError(
          `Only ${data.available} waiting (you asked for ${data.requested}); all remaining were notified.`
        );
      }
      if (data.remaining != null) {
        setDash((prev) => {
          if (!prev?.counts) return prev;
          const waiting = data.remaining;
          return {
            ...prev,
            counts: {
              ...prev.counts,
              waiting,
              in_queue: waiting,
              unscheduled: waiting,
              remaining: waiting,
              total: waiting,
            },
          };
        });
      }
      softRefresh();
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
      // Reflect check-in in the live batch table immediately
      const entryId = data?.entry?.id;
      if (entryId && data?.entry?.status) {
        setNotifyResult((prev) => {
          if (!prev?.students?.length) return prev;
          const next = {
            ...prev,
            students: prev.students.map((s) =>
              s.queue_entry_id === entryId
                ? { ...s, status: data.entry.status }
                : s
            ),
          };
          notifyResultRef.current = next;
          return next;
        });
      }
      softRefresh();
    } catch (err) {
      setVerifyError(err.message || 'Invalid or already-used secret code.');
      setVerified(null);
      setVerifyMessage('');
    } finally {
      setVerifyBusy(false);
    }
  }

  async function complete(decision) {
    if (!verified?.entry?.id || completeBusy) return;
    const entryId = verified.entry.id;
    setCompleteBusy(decision);
    setVerifyError('');
    try {
      const data = await api('/admin/complete-verification/', {
        method: 'POST',
        body: {
          queue_entry_id: entryId,
          decision,
          notes: '',
        },
      });
      setVerifyMessage(data.message || `Marked as ${decision}.`);

      // 1) Stats + Available to schedule update immediately
      if (data.counts) {
        setDash((prev) =>
          prev ? { ...prev, counts: data.counts } : { counts: data.counts }
        );
      }

      // 2) Batch result table — drop the student / replace with server payload
      if (data.batch?.batch) {
        setNotifyResult(data.batch);
        notifyResultRef.current = data.batch;
      } else if (data.removed_queue_entry_id) {
        setNotifyResult((prev) => {
          if (!prev?.students?.length) return prev;
          const nextStudents = prev.students.filter(
            (s) => s.queue_entry_id !== data.removed_queue_entry_id
          );
          const remainNote =
            decision === 'back_to_queue'
              ? `Returned to waiting nearer the front — ${nextStudents.length} remain in today’s batch.`
              : decision === 'rejected'
                ? `Deleted from batch table — ${nextStudents.length} remain.`
                : `Student approved. Removed from batch table — ${nextStudents.length} remain.`;
          const next = {
            ...prev,
            students: nextStudents,
            notified_count: nextStudents.length,
            remaining_in_batch: nextStudents.length,
            message: remainNote,
          };
          notifyResultRef.current = next;
          return next;
        });
      }

      // 3) Live queue table
      if (decision === 'back_to_queue' && data.entry) {
        setQueue((prev) => {
          const without = prev.filter((row) => row.id !== entryId);
          // Default list is waiting-only — show them again after return
          if (!status || status === 'waiting') {
            return [data.entry, ...without];
          }
          return without;
        });
      } else {
        setQueue((prev) => prev.filter((row) => row.id !== entryId));
      }

      setVerified(null);
      setSecretCode('');
      softRefresh();
    } catch (err) {
      setVerifyError(err.message || 'Could not complete verification.');
    } finally {
      setCompleteBusy(null);
    }
  }

  async function rescheduleEntry(queueEntryId, nextDate) {
    setQueueBusy(true);
    setQueueError('');
    setQueueMessage('');
    setRescheduleError('');
    try {
      const data = await api('/admin/reschedule/', {
        method: 'POST',
        body: {
          queue_entry_id: queueEntryId,
          scheduled_date: nextDate,
          channel,
        },
      });
      setQueueMessage(data.message || 'Rescheduled.');
      setRescheduleMessage(data.message || 'Student rescheduled.');
      if (data.batch || Array.isArray(data.students)) {
        const payload = {
          ...data,
          batch: data.batch,
          students: Array.isArray(data.students) ? data.students : [],
          delivery_pending: data.delivery_pending !== false,
          rescheduled: true,
          remaining_in_batch:
            data.remaining_in_batch ??
            (Array.isArray(data.students) ? data.students.length : 0),
        };
        setNotifyResult(payload);
        notifyResultRef.current = payload;
        if (payload.delivery_pending && payload.batch?.id) {
          void pollBatchDelivery(payload.batch.id, {
            onDone: (final) => {
              setRescheduleMessage(
                deliverySummaryMessage(
                  final,
                  data.message || 'Student rescheduled.'
                )
              );
            },
          });
        }
      }
      softRefresh();
    } catch (err) {
      setQueueError(err.message);
      setRescheduleError(err.message || 'Could not reschedule this student.');
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
      notifyResultRef.current = data;
      setRescheduleMessage(
        data.delivery_pending
          ? `${data.message || 'Batch rescheduled.'} Confirming email/SMS…`
          : deliverySummaryMessage(data, data.message || 'Batch rescheduled.')
      );
      if (data.remaining != null) {
        setDash((prev) => {
          if (!prev?.counts) return prev;
          const waiting = data.remaining;
          return {
            ...prev,
            counts: {
              ...prev.counts,
              waiting,
              in_queue: waiting,
              unscheduled: waiting,
              remaining: waiting,
              total: waiting,
            },
          };
        });
      }
      if (data.delivery_pending !== false && data.batch?.id) {
        void pollBatchDelivery(data.batch.id, {
          onDone: (final) => {
            setRescheduleMessage(
              deliverySummaryMessage(
                final,
                data.message || 'Batch rescheduled.'
              )
            );
          },
        });
      }
      softRefresh();
      return true;
    } catch (err) {
      setRescheduleError(err.message || 'Could not reschedule this batch.');
      return false;
    } finally {
      setRescheduleBusy(false);
    }
  }

  const stageHint =
    waitingCount > 0
      ? `${waitingCount} unscheduled in queue`
      : liveBatchOpen
        ? 'Batch open · verify codes'
        : 'Waiting for campus joiners';

  return (
    <section className="dash desk-dash kabque-ops">
      <header className="desk-welcome">
        <div className="desk-welcome-copy">
          <p className="desk-welcome-kicker">Kabale University · Supervisor</p>
          <h1>Desk control</h1>
          <p className="desk-welcome-lede">{stageHint}</p>
        </div>
        <div className="desk-welcome-actions">
          {lastSynced ? (
            <span className="dash-refreshed desk-live-pill">
              <span className="desk-live-dot" aria-hidden="true" />
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
            <p className="desk-zone-kicker">Operations</p>
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
            completeBusy={completeBusy}
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
            <p className="desk-zone-kicker">Today</p>
            <h2 id="desk-batch-heading">Batch results</h2>
          </div>
        </header>
        <BatchResultTable
          result={notifyResult}
          onBatchReschedule={batchReschedule}
          onStudentReschedule={rescheduleEntry}
          rescheduleBusy={rescheduleBusy}
          rescheduleError={rescheduleError}
          rescheduleMessage={rescheduleMessage}
          studentRescheduleBusy={queueBusy}
        />
      </section>

      <section className="desk-zone" aria-labelledby="desk-queue-heading">
        <header className="desk-zone-head">
          <div>
            <p className="desk-zone-kicker">Queue</p>
            <h2 id="desk-queue-heading">Waiting students</h2>
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
