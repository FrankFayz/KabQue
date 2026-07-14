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
      setPageError('');
    } catch (err) {
      setPageError(err.message);
    }
  }, [status, search]);

  useEffect(() => {
    load();
    const id = setInterval(load, 10000);
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
      // Keep the notify form alert short; full batch details render below.
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
      await load();
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
      await load();
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
      setVerified(null);
      setSecretCode('');
      await load();
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
      await load();
    } catch (err) {
      setQueueError(err.message);
    } finally {
      setQueueBusy(false);
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
            <button
              type="button"
              className="btn btn-primary"
              onClick={load}
              disabled={notifyBusy || verifyBusy || queueBusy}
            >
              Refresh
            </button>
          </div>
        }
      />

      <Alert>{pageError}</Alert>
      <Alert>{queueError}</Alert>
      <Alert variant="info">{!queueError ? queueMessage : ''}</Alert>
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
          remaining={dash?.counts?.remaining ?? dash?.counts?.waiting ?? 0}
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

      <BatchResultTable result={notifyResult} />
      <QueueTable
        queue={queue}
        status={status}
        search={search}
        busy={queueBusy}
        onStatusChange={setStatus}
        onSearchChange={setSearch}
        onReschedule={rescheduleEntry}
      />
    </section>
  );
}
