import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import AdminStats from '../components/admin/AdminStats';
import AnalyticsBreakdown from '../components/admin/AnalyticsBreakdown';
import BatchResultTable from '../components/admin/BatchResultTable';
import NotifyBatchForm from '../components/admin/NotifyBatchForm';
import QueueTable from '../components/admin/QueueTable';
import VerifyCodePanel from '../components/admin/VerifyCodePanel';
import Alert from '../components/ui/Alert';
import PageHeader from '../components/ui/PageHeader';

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
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [lastSynced, setLastSynced] = useState(null);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (status) params.set('status', status);
      if (search) params.set('search', search);
      const bust = `_=${Date.now()}`;
      const [d, q] = await Promise.all([
        api(`/admin/dashboard/?${bust}`),
        api(`/admin/queue/?${params.toString()}&${bust}`),
      ]);
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
      setError('');
    } catch (err) {
      setError(err.message);
    }
  }, [status, search]);

  useEffect(() => {
    load();
    // Live counts: refresh when students join or leave
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  async function notifyBatch(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
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
      setMessage(data.message || `Notified ${data.notified_count} student(s).`);
      if (data.shortage) {
        setError(
          `Only ${data.available} student(s) were waiting (you asked for ${data.requested}). All remaining waiters were notified.`
        );
      }
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const data = await api('/admin/verify-code/', {
        method: 'POST',
        body: { secret_code: secretCode },
      });
      setVerified(data);
      setMessage(data.message);
      await load();
    } catch (err) {
      setError(err.message);
      setVerified(null);
    } finally {
      setBusy(false);
    }
  }

  async function complete(decision) {
    if (!verified?.entry?.id) return;
    setBusy(true);
    setError('');
    try {
      await api('/admin/complete-verification/', {
        method: 'POST',
        body: {
          queue_entry_id: verified.entry.id,
          decision,
          notes: '',
        },
      });
      setMessage(`Marked as ${decision}.`);
      setVerified(null);
      setSecretCode('');
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function rescheduleEntry(queueEntryId, nextDate) {
    setBusy(true);
    setError('');
    try {
      const data = await api('/admin/reschedule/', {
        method: 'POST',
        body: {
          queue_entry_id: queueEntryId,
          scheduled_date: nextDate,
        },
      });
      setMessage(data.message || 'Rescheduled.');
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function removeEntry(row) {
    const name = row.student?.full_name || row.student?.registration_number || 'student';
    const ok = window.confirm(`Remove ${name} from the queue?`);
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      const data = await api('/admin/remove-from-queue/', {
        method: 'POST',
        body: { queue_entry_id: row.id },
      });
      setMessage(data.message || 'Removed from queue.');
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="dash">
      <PageHeader
        eyebrow="Admin desk"
        title="KabQue control"
        action={
          <div className="dash-actions">
            {lastSynced && (
              <span className="dash-refreshed">
                Live · {lastSynced.toLocaleTimeString()}
              </span>
            )}
            <button type="button" className="btn btn-primary" onClick={load} disabled={busy}>
              Refresh
            </button>
          </div>
        }
      />

      <Alert>{error}</Alert>
      <Alert variant="info">{message}</Alert>
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
          busy={busy}
          remaining={dash?.counts?.remaining ?? dash?.counts?.waiting ?? 0}
          onBatchSizeChange={setBatchSize}
          onScheduledDateChange={setScheduledDate}
          onChannelChange={setChannel}
          onSubmit={notifyBatch}
        />
        <VerifyCodePanel
          secretCode={secretCode}
          verified={verified}
          busy={busy}
          onSecretCodeChange={setSecretCode}
          onVerify={verifyCode}
          onComplete={complete}
        />
      </div>

      <BatchResultTable result={notifyResult} />
      <QueueTable
        queue={queue}
        status={status}
        search={search}
        busy={busy}
        onStatusChange={setStatus}
        onSearchChange={setSearch}
        onReschedule={rescheduleEntry}
        onRemove={removeEntry}
      />
    </section>
  );
}
