import { useEffect, useRef, useState, type ReactNode } from "react";

import { usePreferences } from "../settings/preferences";

interface Props {
  name: string;
  shortcut?: string;
  text: string;
  // beside the element (tool rail), above it (bars at the bottom of the screen) or below it (the page's top bar)
  place?: "right" | "top" | "bottom";
  children: ReactNode;
}

const DELAY = 600;

// a short explanation after the pointer rests on an element; it floats, so nothing moves
export default function Hint({ name, shortcut, text, place = "right", children }: Props) {
  const anchor = useRef<HTMLSpanElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const timer = useRef(0);
  const [open, setOpen] = useState(false);
  const [{ hints }] = usePreferences();

  const hide = () => {
    window.clearTimeout(timer.current);
    setOpen(false);
  };

  useEffect(() => () => window.clearTimeout(timer.current), []);

  useEffect(() => {
    if (!open || !anchor.current || !box.current) return;
    const r = anchor.current.getBoundingClientRect();
    const h = box.current.offsetHeight;
    const top = place === "top" ? r.top - h - 8 : place === "bottom" ? r.bottom + 8 : Math.min(window.innerHeight - h - 8, r.top + 8);
    const left = place === "right" ? r.right + 8 : Math.min(r.left, window.innerWidth - box.current.offsetWidth - 8);
    box.current.style.left = `${left}px`;
    box.current.style.top = `${Math.max(8, top)}px`;
    box.current.style.visibility = "visible";
  }, [open, place]);

  return (
    <span
      ref={anchor}
      className="hint-anchor"
      onPointerEnter={() => {
        window.clearTimeout(timer.current);
        if (!hints) return;
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
