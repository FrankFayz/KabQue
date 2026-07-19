import { useCallback, useEffect, useState } from 'react';
import { api, getStoredUser, setAuth } from '../api';
import CompleteProfileCard from '../components/student/CompleteProfileCard';
import DeskOutcomeCard from '../components/student/DeskOutcomeCard';
import JoinQueueCard from '../components/student/JoinQueueCard';
import QueueStatusBoard from '../components/student/QueueStatusBoard';
import Alert from '../components/ui/Alert';

function deskOutcomeFrom(data, profile) {
  const raw =
    data?.desk_outcome ||
    profile?.desk_outcome ||
    data?.profile?.desk_outcome ||
    '';
  const o = String(raw).trim().toLowerCase();
  return o === 'approved' || o === 'rejected' ? o : '';
}

function StudentDashboard() {
  const [user, setUser] = useState(() => getStoredUser());
  const [queue, setQueue] = useState(null);
  const [profile, setProfile] = useState(null);
  const [inQueue, setInQueue] = useState(false);
  const [deskOutcome, setDeskOutcome] = useState(() =>
    deskOutcomeFrom(getStoredUser())
  );
  const [profileComplete, setProfileComplete] = useState(
    () => Boolean(getStoredUser()?.profile_complete)
  );
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [showRejoinHint, setShowRejoinHint] = useState(false);
  const [booted, setBooted] = useState(false);

  const applyQueuePayload = useCallback((data) => {
    const complete = Boolean(data?.profile_complete ?? data?.profile?.profile_complete);
    setProfileComplete(complete);

    const nextProfile = data?.in_queue === false ? data.profile || null : data?.student || data?.profile || null;
    const outcome = deskOutcomeFrom(data, nextProfile);

    if (data?.in_queue === false) {
      setInQueue(false);
      setQueue(null);
      setProfile(nextProfile);
      setDeskOutcome(outcome);
      if (outcome) setShowRejoinHint(false);
      return;
    }
    setInQueue(true);
    setQueue(data);
    setProfile(nextProfile);
    setDeskOutcome('');
    setShowRejoinHint(false);
  }, []);

  const load = useCallback(
    async ({ manual = false, includeMe = false } = {}) => {
      if (manual) {
        setRefreshing(true);
        setInfo('');
      }
      setError('');

      try {
        // Prefer one round-trip: /student/queue already returns profile fields.
        // Only hit /auth/me when explicitly requested.
        if (includeMe) {
          const me = await api('/auth/me/');
          if (me?.user) {
            setUser(me.user);
            setAuth({ user: me.user });
            const seeded = deskOutcomeFrom(me.user, me.profile);
            if (seeded) setDeskOutcome(seeded);
          }
          if (typeof me?.profile_complete === 'boolean') {
            setProfileComplete(me.profile_complete);
          }
          if (me?.profile) {
            setProfile(me.profile);
            const meOutcome = deskOutcomeFrom(me, me.profile);
            if (meOutcome) setDeskOutcome(meOutcome);
          }
        }

        const data = await api(`/student/queue/?_=${Date.now()}`);
        applyQueuePayload(data);
        setLastRefreshed(new Date());
        if (manual) {
          const outcome = deskOutcomeFrom(data, data?.profile);
          if (outcome === 'approved') {
            setInfo('Your documents were approved. Queue access is closed.');
          } else if (outcome === 'rejected') {
            setInfo('Your desk visit is complete. Queue access is closed.');
          } else if (data?.in_queue) {
            const num =
              data.position != null && data.status !== 'waiting'
                ? ` · queue #${data.position}`
                : '';
            setInfo(`Queue updated · ${data.status}${num}`);
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
        setBooted(true);
        if (manual) setRefreshing(false);
      }
    },
    [applyQueuePayload]
  );

  useEffect(() => {
    // Skip /auth/me on boot — login already stored the user; queue covers profile.
    load({ manual: false, includeMe: false });
    const tick = () => {
      if (document.hidden) return;
      load({ manual: false, includeMe: false });
    };
    const ms = queue?.day_progress ? 15000 : 45000;
    const id = setInterval(tick, ms);
    const onVis = () => {
      if (!document.hidden) load({ manual: false, includeMe: false });
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [load, queue?.day_progress]);

  async function handleProfileSaved(data) {
    if (data?.user) {
      setUser(data.user);
      setAuth({ user: data.user });
    }
    if (data?.profile) setProfile(data.profile);
    setProfileComplete(true);
    setInfo(data?.message || 'Profile saved.');
    await load({ manual: true, includeMe: false });
  }

  async function handleJoined() {
    await load({ manual: true, includeMe: false });
  }

  async function handleReschedule() {
    setActionBusy(true);
    setError('');
    try {
      const data = await api('/student/reschedule/', {
        method: 'POST',
        body: {},
      });
      setInfo(
        data.message ||
          'Returned to the waiting queue. Wait for the next supervisor schedule.'
      );
      if (data.queue) applyQueuePayload(data.queue);
      else await load({ manual: true, includeMe: false });
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
      const data = await api('/student/leave-queue/', { method: 'POST', body: {} });
      setInfo(
        data.message ||
          'You left the queue. You can rejoin on campus whenever you are ready.'
      );
      applyQueuePayload({
        in_queue: false,
        profile_complete: data.profile_complete ?? profileComplete,
        profile: data.profile || profile,
      });
      if (data.can_rejoin !== false) setShowRejoinHint(true);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setActionBusy(false);
    }
  }

  function handleProfileUpdated(data) {
    if (data?.user) {
      setUser(data.user);
      setAuth({ user: data.user });
    }
    if (data?.profile) setProfile(data.profile);
  }

  const name =
    user?.full_name || user?.username || profile?.full_name || 'Student';
  const reg = user?.registration_number || profile?.registration_number;
  const finalized = Boolean(deskOutcome);

  return (
    <section className="dash student-dash">
      <header className="student-welcome">
        <div className="student-welcome-copy">
          <p className="student-welcome-kicker">Student</p>
          <h1>Welcome, {name}</h1>
          <p className="student-welcome-lede">
            {finalized
              ? 'Your KabQue desk visit is complete'
              : 'Track your place in the KabQue fresher queue'}
            {reg ? (
              <>
                {' · '}
                <span className="student-welcome-reg">{reg}</span>
              </>
            ) : null}
          </p>
        </div>
        <div className="student-welcome-actions">
          {lastRefreshed ? (
            <span className="dash-refreshed">
              Updated {lastRefreshed.toLocaleTimeString()}
            </span>
          ) : null}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => load({ manual: true, includeMe: false })}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      <Alert>{error}</Alert>
      <Alert variant="info">{!error ? info : ''}</Alert>

      <div className="student-dash-body">
        {!booted ? (
          <p className="muted student-boot">Loading your queue status…</p>
        ) : inQueue ? (
          <QueueStatusBoard
            queue={queue}
            busy={actionBusy}
            onReschedule={handleReschedule}
            onLeave={handleLeaveQueue}
          />
        ) : finalized ? (
          <DeskOutcomeCard profile={profile} outcome={deskOutcome} />
        ) : !profileComplete ? (
          <CompleteProfileCard profile={profile} onSaved={handleProfileSaved} />
        ) : (
          <JoinQueueCard
            profile={profile}
            onJoined={handleJoined}
            onProfileUpdated={handleProfileUpdated}
            joinDisabled={finalized}
            showRejoinHint={showRejoinHint}
          />
        )}
      </div>
    </section>
  );
}

export default StudentDashboard;
