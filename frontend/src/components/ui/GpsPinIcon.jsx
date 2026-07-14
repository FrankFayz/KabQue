/** Professional GPS location pin icon for join-queue status. */
export default function GpsPinIcon({ className = '', size = 28 }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <circle cx="24" cy="24" r="22" fill="currentColor" opacity="0.1" />
      <path
        d="M24 8c-6.075 0-11 4.925-11 11 0 8.25 11 21 11 21s11-12.75 11-21c0-6.075-4.925-11-11-11Z"
        fill="currentColor"
        opacity="0.95"
      />
      <circle cx="24" cy="19" r="4.25" fill="#fff" />
      <circle cx="24" cy="19" r="2" fill="currentColor" opacity="0.85" />
    </svg>
  );
}
