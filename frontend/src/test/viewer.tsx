import { forwardRef } from "react";

// stands in for the Cornerstone viewer, which needs WebGL; a click is one brush stroke
const Viewer = forwardRef<unknown, { onEdit?: () => void }>(function Viewer({ onEdit }) {
  return (
    <button type="button" onClick={onEdit}>
      brush stroke
    </button>
  );
});

export default Viewer;
