const PATHS: Record<string, JSX.Element> = {
  brush: <path d="M10.5 2.5l3 3-6.5 6.5H4V9z M9 4l3 3" />,
  // a brush above a closed outline: paints up to the edge of the lesion
  threshold: <path d="M12 1.5l2.5 2.5-4.5 4.5H7.5V6z M10.5 3l2.5 2.5 M5.5 8.5c-2.2 0-4 1.4-4 3.2s1.8 2.8 4 2.8 4-1 4-2.8" />,
  slice: (
    <>
      <path d="M2.5 12.5h11 M2.5 9.5h11" strokeDasharray="1.6 2" />
      <path d="M6 6.5h4.5a2.5 2.5 0 0 0 0-5H6 M8 0.2L6 1.5 8 3" />
    </>
  ),
  three: <path d="M2 3h12v10H2z M10 3v10 M10 8h4" />,
  one: <path d="M2 3h12v10H2z" />,
  hideSide: <path d="M2.5 3.5h11v9h-11z M10 3.5v9 M5 8h3 M6.5 6.5L8 8 6.5 9.5" />,
  showSide: <path d="M2.5 3.5h11v9h-11z M10 3.5v9 M8 8H5 M6.5 6.5L5 8l1.5 1.5" />,
  eraser: <path d="M6 13.5h7.5 M2.5 10l6-6.5 4.5 4.5-5.5 5.5H6z M5.5 7l4.5 4.5" />,
  undo: <path d="M4.5 6.5h6a3.5 3.5 0 0 1 0 7H7 M7 3.5l-3 3 3 3" />,
  fill: (
    <>
      <path d="M2.5 3h11 M2.5 13h11" />
      <path d="M2.5 8h11" strokeDasharray="1.6 2" />
      <path d="M8 4.5v7 M6.2 6.2L8 4.5l1.8 1.7 M6.2 9.8L8 11.5l1.8-1.7" />
    </>
  ),
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
