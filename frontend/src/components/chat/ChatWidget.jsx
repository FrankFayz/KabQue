import { useEffect, useRef, useState } from 'react';
import { api, getStoredUser, userError } from '../../api';
import { isStudent } from '../../authRoles';
import './ChatWidget.css';

const GREETING = {
  role: 'assistant',
  content:
    "Hi! I'm KabQue Assistant. Ask me where you are in the queue, what documents to bring, or how joining works.",
};

const SUGGESTIONS = [
  'Where am I in the queue?',
  'What documents do I need?',
  "Why can't I join the queue?",
];

export default function ChatWidget() {
  const user = getStoredUser();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([GREETING]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  // Students only for the first version.
  if (!user || !isStudent(user)) return null;

  async function send(text) {
    const content = text.trim();
    if (!content || busy) return;
    const next = [...messages, { role: 'user', content }];
    setMessages(next);
    setInput('');
    setBusy(true);
    try {
      // Drop the local greeting; the backend needs to start on a user turn.
      const history = next.filter((m) => m !== GREETING);
      const data = await api('/chat/', { method: 'POST', body: { messages: history } });
      setMessages([...next, { role: 'assistant', content: data.reply }]);
    } catch (err) {
      setMessages([
        ...next,
        { role: 'assistant', content: userError(err, 'Sorry, I could not reply. Try again.') },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat-widget">
      {open && (
        <div className="chat-panel" role="dialog" aria-label="KabQue Assistant">
          <div className="chat-head">
            <strong>KabQue Assistant</strong>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close">×</button>
          </div>
          <div className="chat-body">
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg chat-${m.role}`}>{m.content}</div>
            ))}
            {messages.length === 1 && (
              <div className="chat-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            )}
            {busy && <div className="chat-msg chat-assistant chat-typing">…</div>}
            <div ref={endRef} />
          </div>
          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your question…"
              maxLength={1000}
            />
            <button type="submit" disabled={busy || !input.trim()}>Send</button>
          </form>
        </div>
      )}
      <button type="button" className="chat-fab" onClick={() => setOpen((o) => !o)}>
        {open ? 'Close' : 'Need help?'}
      </button>
    </div>
  );
}
