import { useRef, useState, type ReactNode } from "react";

import { filesFromDrop } from "./files";

interface Props {
  title: string;
  body: string;
  accept?: string;
  multiple?: boolean;
  folderLabel?: string;
  filesLabel: string;
  onFiles: (files: File[]) => void;
  children?: ReactNode;
}

export default function DropZone({ title, body, accept, multiple = true, folderLabel, filesLabel, onFiles, children }: Props) {
  const [over, setOver] = useState(false);
  const filesInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  const pick = (list: FileList | null) => {
    if (list && list.length > 0) onFiles(Array.from(list));
  };

  return (
    <div
      className={over ? "drop drop--over" : "drop"}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={async (event) => {
        event.preventDefault();
        setOver(false);
        const files = await filesFromDrop(event.dataTransfer.items);
        if (files.length > 0) onFiles(multiple ? files : files.slice(0, 1));
      }}
    >
      <b>{title}</b>
      <p>{body}</p>
      <div className="drop__buttons">
        {folderLabel && (
          <button type="button" className="btn btn--small" onClick={() => folderInput.current?.click()}>
            {folderLabel}
          </button>
        )}
        <button type="button" className="btn btn--small" onClick={() => filesInput.current?.click()}>
          {filesLabel}
        </button>
      </div>
      {children}
      <input ref={filesInput} type="file" hidden multiple={multiple} accept={accept} onChange={(event) => pick(event.target.files)} />
      {folderLabel && (
        <input
          ref={folderInput}
          type="file"
          hidden
          // @ts-expect-error webkitdirectory isn't in React's input types
          webkitdirectory=""
          onChange={(event) => pick(event.target.files)}
        />
      )}
    </div>
  );
}
