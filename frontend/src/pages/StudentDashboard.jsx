import { useCallback, useEffect, useState } from 'react';
import { api, getStoredUser, setAuth } from '../api';
import CompleteProfileCard from '../components/student/CompleteProfileCard';
import JoinQueueCard from '../components/student/JoinQueueCard';
import QueueStatusBoard from '../components/student/QueueStatusBoard';
import Alert from '../components/ui/Alert';
import PageHeader from '../components/ui/PageHeader';

export default function StudentDashboard() {
  const [user, setUser] = useState(() => getStoredUser());
  const [queue, setQueue] = useState(null);
  const [profile, setProfile] = useState(null);
  const [inQueue, setInQueue] = useState(false);
  const [profileComplete, setProfileComplete] = useState(
    () => Boolean(getStoredUser()?.profile_complete)
  );
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);

  const applyQueuePayload = useCallback((data) => {
    const complete = Boolean(data?.profile_complete ?? data?.profile?.profile_complete);
    setProfileComplete(complete);

    if (data?.in_queue === false) {
      setInQueue(false);
      setQueue(null);
      setProfile(data.profile || null);
      return;
    }
    setInQueue(true);
    setQueue(data);
    setProfile(data.student || null);
  }, []);

  const load = useCallback(
    async ({ manual = false } = {}) => {
      if (manual) {
        setRefreshing(true);
        setInfo('');
      }
      setError('');

      try {
        const me = await api('/auth/me/');
        if (me?.user) {
          setUser(me.user);
          setAuth({ user: me.user });
        }
        if (typeof me?.profile_complete === 'boolean') {
          setProfileComplete(me.profile_complete);
        }
        if (me?.profile) setProfile(me.profile);

        const data = await api(`/student/queue/?_=${Date.now()}`);
        applyQueuePayload(data);
        setLastRefreshed(new Date());
        if (manual) {
          if (data?.in_queue) {
            setInfo(`Queue updated · position #${data.position} · ${data.status}`);
          } else if (!(data?.profile_complete ?? data?.profile?.profile_complete)) {
            setInfo('Complete your profile before joining the queue.');
          } else {
            setInfo('Status updated · ready to join the queue on campus');
          }
        }
      } catch (err) {
        setError(err.message || 'Could not refresh queue status.');
        setInfo('');
      } finally {
        if (manual) setRefreshing(false);
      }
    },
    [applyQueuePayload]
  );

  useEffect(() => {
    load({ manual: false });
    const id = setInterval(() => load({ manual: false }), 30000);
    return () => clearInterval(id);
  }, [load]);

  async function handleProfileSaved(data) {
    if (data?.user) {
      setUser(data.user);
      setAuth({ user: data.user });
    }
    if (data?.profile) setProfile(data.profile);
    setProfileComplete(true);
    setInfo(data?.message || 'Profile saved.');
    await load({ manual: true });
  }

  async function handleJoined() {
    await load({ manual: true });
  }

  async function handleReschedule(scheduledDate) {
    setActionBusy(true);
    setError('');
    try {
      const data = await api('/student/reschedule/', {
        method: 'POST',
        body: { scheduled_date: scheduledDate },
      });
      setInfo(data.message || 'Rescheduled.');
      if (data.queue) applyQueuePayload(data.queue);
      else await load({ manual: true });
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setActionBusy(false);
    }
  }

  async function handleLeaveQueue() {
    setActionBusy(true);
    setError('');
    try {
      const data = await api('/student/leave-queue/', { method: 'POST' });
      setInfo(data.message || 'You left the queue.');
      setInQueue(false);
      setQueue(null);
      if (data.profile) setProfile(data.profile);
      if (typeof data.profile_complete === 'boolean') {
        setProfileComplete(data.profile_complete);
      }
      await load({ manual: true });
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setActionBusy(false);
    }
  }

  const greeting =
    user?.full_name ||
    profile?.full_name ||
    profile?.registration_number ||
    user?.registration_number ||
    'student';

  return (
    <section className="dash">
      <PageHeader
        eyebrow="Student dashboard"
        title={`Hello, ${greeting}`}
        action={
          <div className="dash-actions">
            {lastRefreshed && (
              <span className="dash-refreshed">
                Updated {lastRefreshed.toLocaleTimeString()}
              </span>
            )}
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => load({ manual: true })}
              disabled={refreshing}
            >
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        }
      />
      <Alert>{error}</Alert>
      <Alert variant="info">{!error ? info : ''}</Alert>

      {inQueue ? (
        <QueueStatusBoard
          queue={queue}
          busy={actionBusy}
          onReschedule={handleReschedule}
          onLeave={handleLeaveQueue}
        />
      ) : !profileComplete ? (
        <CompleteProfileCard profile={profile} onSaved={handleProfileSaved} />
      ) : (
        <JoinQueueCard profile={profile} onJoined={handleJoined} />
      )}
    </section>
  );
}
