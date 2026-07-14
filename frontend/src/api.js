const configured = (import.meta.env.VITE_API_URL || '').trim().replace(/\/$/, '');

// Never call the Vercel frontend host for API — always use Render in production.
const API_URL =
  configured && /^https?:\/\//i.test(configured)
    ? configured
    : import.meta.env.PROD
      ? 'https://kabque.onrender.com/api'
      : '/api';
