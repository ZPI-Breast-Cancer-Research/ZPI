import { useEffect, useRef, useState, type CSSProperties } from "react";

import "./select.css";

interface Props {
  id: string;
  value: string;
  options: readonly string[];
  label?: (value: string) => string;
  // shown while nothing is picked
  placeholder?: string;
  // the model's answer, marked in the list only
  mark?: { value: string; text: string };
  ariaLabel?: string;
  className?: string;
  // opened in place of a value that was just clicked
  startOpen?: boolean;
  onChange: (value: string) => void;
}

// a list in the app's own look instead of the system one; arrows, Enter and Esc work as in a select
export default function Select({ id, value, options, mark, placeholder = "—", ariaLabel, className, startOpen, onChange, label = (v) => v }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  // the form scrolls and would clip the list, so it floats above the page next to the field
  const [place, setPlace] = useState<CSSProperties>({});

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => !box.current?.contains(event.target as Node) && setOpen(false);
    const shut = () => setOpen(false);
    document.addEventListener("mousedown", close);
    window.addEventListener("scroll", shut, true);
    window.addEventListener("resize", shut);
    return () => {
      document.removeEventListener("mousedown", close);
      window.removeEventListener("scroll", shut, true);
      window.removeEventListener("resize", shut);
    };
  }, [open]);

  const show = () => {
    const r = box.current!.getBoundingClientRect();
    const height = options.length * 30 + 8;
    // opens upwards when there is no room below the field
    const up = window.innerHeight - r.bottom < height + 8 && r.top > height + 8;
    setPlace({ left: r.left, width: r.width, ...(up ? { bottom: window.innerHeight - r.top + 2 } : { top: r.bottom + 2 }) });
    setActive(Math.max(0, options.indexOf(value)));
    setOpen(true);
  };
  useEffect(() => {
    if (!startOpen) return;
    box.current?.querySelector("button")?.focus({ preventScroll: true });
    show();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const pick = (option: string) => {
    onChange(option);
    setOpen(false);
  };

  return (
    <div className={className ? `field-select ${className}` : "field-select"} ref={box}>
      <button
        id={id}
        type="button"
        className="field-select__button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (!open) return show();
            setActive((i) => (i + (event.key === "ArrowDown" ? 1 : options.length - 1)) % options.length);
          } else if (event.key === "Enter" && open) {
            event.preventDefault();
            pick(options[active]);
          } else if (event.key === "Escape" && open) {
            // the review screen's Esc (show the form) should not fire too
            event.stopPropagation();
            setOpen(false);
          }
        }}
      >
        {(value && label(value)) || placeholder}
      </button>
      {open && (
        <ul className="field-select__list" role="listbox" aria-labelledby={id} style={place}>
          {options.map((option, i) => (
            <li
              key={option}
              role="option"
              aria-selected={option === value}
              className={i === active ? "field-select__option field-select__option--active" : "field-select__option"}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => pick(option)}
            >
              {label(option)}
              {option === mark?.value && <small>{mark.text}</small>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
