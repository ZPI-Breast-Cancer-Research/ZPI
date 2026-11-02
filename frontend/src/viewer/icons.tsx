const PATHS: Record<string, JSX.Element> = {
  brush: <path d="M10.5 2.5l3 3-6.5 6.5H4V9z M9 4l3 3" />,
  threshold: (
    <>
      <path d="M2.5 4h11 M2.5 8h11 M2.5 12h11" />
      <circle cx="6" cy="4" r="1.6" className="icon__knob" />
      <circle cx="10.5" cy="8" r="1.6" className="icon__knob" />
      <circle cx="5" cy="12" r="1.6" className="icon__knob" />
    </>
  ),
  eraser: <path d="M6 13.5h7.5 M2.5 10l6-6.5 4.5 4.5-5.5 5.5H6z M5.5 7l4.5 4.5" />,
  undo: <path d="M4.5 6.5h6a3.5 3.5 0 0 1 0 7H7 M7 3.5l-3 3 3 3" />,
  pan: <path d="M8 1.5v13 M1.5 8h13 M6 3.5l2-2 2 2 M6 12.5l2 2 2-2 M3.5 6l-2 2 2 2 M12.5 6l2 2-2 2" />,
  window: (
    <>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor" stroke="none" />
    </>
  ),
  eye: (
    <>
      <path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" />
      <circle cx="8" cy="8" r="2" />
    </>
  ),
};

export default function Icon({ name }: { name: string }) {
  return (
    <svg className="icon" viewBox="0 0 16 16" aria-hidden="true">
      {PATHS[name]}
    </svg>
  );
}
