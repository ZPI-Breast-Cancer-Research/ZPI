import { useEffect, useRef, useState } from "react";

import { t } from "../i18n";

interface Props {
  id: string;
  value: string;
  options: string[];
  // the model's answer, marked in the list only, so the closed field shows the value alone
  proposal: string;
  onChange: (value: string) => void;
}

// a list in the app's own look instead of the system one; arrows, Enter and Esc work as in a select
export default function FieldSelect({ id, value, options, proposal, onChange }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => !box.current?.contains(event.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const show = () => {
    setActive(Math.max(0, options.indexOf(value)));
    setOpen(true);
  };
  const pick = (option: string) => {
    onChange(option);
    setOpen(false);
  };

  return (
    <div className="field-select" ref={box}>
      <button
        id={id}
        type="button"
        className="field-select__button"
        aria-haspopup="listbox"
        aria-expanded={open}
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
        {value}
      </button>
      {open && (
        <ul className="field-select__list" role="listbox" aria-labelledby={id}>
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
              {option}
              {option === proposal && <small>{t("review.field.model")}</small>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
