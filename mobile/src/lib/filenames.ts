const BAD = /[\u0000-\u001f\u007f<>:"/\\|?*‪-‮⁦-⁩]/g;
const RESERVED = new Set(['con', 'prn', 'aux', 'nul', ...Array.from({ length: 9 }, (_, i) => `com${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `lpt${i + 1}`)]);

export function safeFileName(title: string | null | undefined, ext: string, fallback = 'media', maxLen = 80): string {
  let stem = (title ?? '').normalize('NFKC').replace(BAD, ' ').replace(/\s+/g, ' ').trim().replace(/^[ .\-_]+|[ .\-_]+$/g, '');
  if (!stem || RESERVED.has(stem.toLowerCase())) stem = fallback;
  stem = stem.slice(0, maxLen).replace(/[ .]+$/, '');
  const e = (ext || 'bin').toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 5) || 'bin';
  return `${stem}.${e}`;
}

/** "clip.mp4" → "clip (2).mp4" when the name is taken. */
export function uniqueName(name: string, taken: Set<string>): string {
  if (!taken.has(name.toLowerCase())) return name;
  const dot = name.lastIndexOf('.');
  const stem = dot > 0 ? name.slice(0, dot) : name;
  const ext = dot > 0 ? name.slice(dot) : '';
  for (let i = 2; i < 10_000; i += 1) {
    const candidate = `${stem} (${i})${ext}`;
    if (!taken.has(candidate.toLowerCase())) return candidate;
  }
  return `${stem}-${Date.now()}${ext}`;
}
