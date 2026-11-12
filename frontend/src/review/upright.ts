import { useEffect, useState } from "react";

// page_rotations are counter-clockwise (PIL); redrawn once so the page lays out like any image
export function useUprightImage(url: string | null, angle: number): string | null {
  const turn = ((angle % 360) + 360) % 360;
  const [upright, setUpright] = useState<{ key: string; url: string } | null>(null);
  const key = `${url}|${turn}`;

  useEffect(() => {
    if (!url || !turn) return;
    let cancelled = false;
    let made: string | null = null;
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => {
      const side = turn === 90 || turn === 270;
      const canvas = document.createElement("canvas");
      canvas.width = side ? image.naturalHeight : image.naturalWidth;
      canvas.height = side ? image.naturalWidth : image.naturalHeight;
      const ctx = canvas.getContext("2d")!;
      ctx.translate(canvas.width / 2, canvas.height / 2);
      ctx.rotate((-turn * Math.PI) / 180);
      ctx.drawImage(image, -image.naturalWidth / 2, -image.naturalHeight / 2);
      try {
        canvas.toBlob((blob) => {
          if (cancelled || !blob) return;
          made = URL.createObjectURL(blob);
          setUpright({ key, url: made });
        });
      } catch {
        // another origin without CORS can't be redrawn, so it stays as it came
      }
    };
    image.src = url;
    return () => {
      cancelled = true;
      if (made) URL.revokeObjectURL(made);
    };
  }, [url, turn, key]);

  if (!url) return null;
  if (!turn) return url;
  return upright?.key === key ? upright.url : null;
}
