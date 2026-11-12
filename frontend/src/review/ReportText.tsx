// quotes match loosely (case, Polish letters, spaces, hyphens), like the worker's own check
export default function ReportText({ text, quotes }: { text: string; quotes: string[] }) {
  const ranges = quotes.map((quote) => find(text, quote)).filter((r): r is [number, number] => r !== null);
  ranges.sort((a, b) => a[0] - b[0]);

  const parts: { text: string; mark: boolean }[] = [];
  let at = 0;
  for (const [start, end] of ranges) {
    if (start < at) continue;
    parts.push({ text: text.slice(at, start), mark: false }, { text: text.slice(start, end), mark: true });
    at = end;
  }
  parts.push({ text: text.slice(at), mark: false });

  return (
    <p className="report-text report-text--full">
      {parts.map((part, i) =>
        part.mark ? (
          <mark key={i} className="report-text__quote">
            {part.text}
          </mark>
        ) : (
          part.text
        ),
      )}
    </p>
  );
}

// remembers where each folded character came from, to mark the original
function fold(text: string) {
  let out = "";
  const from: number[] = [];
  for (let i = 0; i < text.length; i++) {
    let ch = text[i].toLowerCase().replace("ł", "l").normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
    if (ch === "-") continue;
    if (/\s/.test(ch)) {
      if (out.endsWith(" ")) continue;
      ch = " ";
    }
    for (const c of ch) {
      out += c;
      from.push(i);
    }
  }
  return { out, from };
}

function find(text: string, quote: string): [number, number] | null {
  const haystack = fold(text);
  const needle = fold(quote).out.trim();
  if (!needle) return null;
  const at = haystack.out.indexOf(needle);
  if (at < 0) return null;
  return [haystack.from[at], haystack.from[at + needle.length - 1] + 1];
}
