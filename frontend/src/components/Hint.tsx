import { useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  name: string;
  shortcut?: string;
  text: string;
  // beside the element (tool rail) or above it (bars at the bottom of the screen)
  place?: "right" | "top";
  children: ReactNode;
}

const DELAY = 600;

// a short explanation after the pointer rests on an element; it floats, so nothing moves
export default function Hint({ name, shortcut, text, place = "right", children }: Props) {
  const anchor = useRef<HTMLSpanElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const timer = useRef(0);
  const [open, setOpen] = useState(false);

  const hide = () => {
    window.clearTimeout(timer.current);
    setOpen(false);
  };

  useEffect(() => () => window.clearTimeout(timer.current), []);

  useEffect(() => {
    if (!open || !anchor.current || !box.current) return;
    const r = anchor.current.getBoundingClientRect();
    const h = box.current.offsetHeight;
    const top = place === "top" ? r.top - h - 8 : Math.min(window.innerHeight - h - 8, r.top + 8);
    box.current.style.left = `${place === "top" ? r.left : r.right + 8}px`;
    box.current.style.top = `${Math.max(8, top)}px`;
    box.current.style.visibility = "visible";
  }, [open, place]);

  return (
    <span
      ref={anchor}
      className="hint-anchor"
      onPointerEnter={() => {
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setOpen(true), DELAY);
      }}
      onPointerLeave={hide}
      onPointerDown={hide}
    >
      {children}
      {open && (
        <div ref={box} className="hint" role="tooltip">
          <div className="hint__head">
            <b>{name}</b>
            {shortcut && <kbd>{shortcut}</kbd>}
          </div>
          {text}
        </div>
      )}
    </span>
  );
}
