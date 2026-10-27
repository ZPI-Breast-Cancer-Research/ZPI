export default function WarningIcon({ label }: { label?: string }) {
  return (
    <svg
      className="warning-icon"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <path d="M8 2L14.5 13.5h-13z" />
      <path d="M8 6.5v3.2M8 11.6v.1" strokeLinecap="round" />
    </svg>
  );
}
