export interface DetectedStudy {
  folder: string;
  dicomFiles: File[];
  report: File | null;
}

export interface GroupedFiles {
  studies: DetectedStudy[];
  unpairedReports: File[];
}

const REPORT_EXT = /\.(txt|jpe?g|png)$/i;
const IGNORED = /(^|\/)(\.DS_Store|Thumbs\.db|desktop\.ini)$/i;

export function isReport(file: File): boolean {
  return REPORT_EXT.test(file.name);
}

function folderOf(file: File): string {
  const path = file.webkitRelativePath || "";
  const cut = path.lastIndexOf("/");
  return cut > 0 ? path.slice(0, cut) : "";
}

// one folder = one study; a report is paired only if it's the only one in that folder
export function groupFiles(files: File[]): GroupedFiles {
  const folders = new Map<string, { dicom: File[]; reports: File[] }>();
  for (const file of files) {
    if (IGNORED.test(file.webkitRelativePath || file.name)) continue;
    const key = folderOf(file);
    const entry = folders.get(key) ?? { dicom: [], reports: [] };
    (isReport(file) ? entry.reports : entry.dicom).push(file);
    folders.set(key, entry);
  }

  const studies: DetectedStudy[] = [];
  const unpairedReports: File[] = [];
  for (const [folder, { dicom, reports }] of folders) {
    if (dicom.length === 0) {
      unpairedReports.push(...reports);
      continue;
    }
    const paired = reports.length === 1 ? reports[0] : null;
    if (!paired) unpairedReports.push(...reports);
    studies.push({ folder: folder || "—", dicomFiles: dicom, report: paired });
  }
  return { studies, unpairedReports };
}

// drag & drop gives directory entries, not File.webkitRelativePath, so walk them by hand
export async function filesFromDrop(items: DataTransferItemList): Promise<File[]> {
  const entries = Array.from(items)
    .map((item) => item.webkitGetAsEntry())
    .filter((entry): entry is FileSystemEntry => entry !== null);
  const out: File[] = [];
  await Promise.all(entries.map((entry) => walk(entry, "", out)));
  return out;
}

async function walk(entry: FileSystemEntry, prefix: string, out: File[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
    Object.defineProperty(file, "webkitRelativePath", { value: prefix + file.name });
    out.push(file);
    return;
  }
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  let batch: FileSystemEntry[];
  do {
    batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
    await Promise.all(batch.map((child) => walk(child, `${prefix}${entry.name}/`, out)));
  } while (batch.length > 0);
}
