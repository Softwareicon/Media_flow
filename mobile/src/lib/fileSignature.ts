/**
 * Magic-byte checks run on the DOWNLOADED file before it is saved anywhere visible.
 * Mirrors backend/app/security/mime.py. A file that isn't real media (an HTML error page,
 * an executable, an archive) is deleted instead of being saved to the photo library.
 */
export type MediaMime =
  | 'video/mp4' | 'video/quicktime' | 'video/webm'
  | 'image/jpeg' | 'image/png' | 'image/gif' | 'image/webp' | 'image/avif' | 'image/heic'
  | 'audio/mpeg' | 'audio/mp4' | 'audio/ogg' | 'audio/wav' | 'audio/flac';

const eq = (b: Uint8Array, off: number, sig: number[]) => sig.every((v, i) => b[off + i] === v);
const ascii = (b: Uint8Array, off: number, len: number) => String.fromCharCode(...Array.from(b.slice(off, off + len)));

export function sniff(b: Uint8Array): MediaMime | null {
  if (b.length < 4) return null;
  if (eq(b, 0, [0xff, 0xd8, 0xff])) return 'image/jpeg';
  if (eq(b, 0, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return 'image/png';
  if (ascii(b, 0, 6) === 'GIF87a' || ascii(b, 0, 6) === 'GIF89a') return 'image/gif';
  if (ascii(b, 0, 4) === 'RIFF' && ascii(b, 8, 4) === 'WEBP') return 'image/webp';
  if (ascii(b, 0, 4) === 'RIFF' && ascii(b, 8, 4) === 'WAVE') return 'audio/wav';
  if (eq(b, 0, [0x1a, 0x45, 0xdf, 0xa3])) return 'video/webm';
  if (ascii(b, 0, 4) === 'OggS') return 'audio/ogg';
  if (ascii(b, 0, 4) === 'fLaC') return 'audio/flac';
  if (ascii(b, 0, 3) === 'ID3' || (b[0] === 0xff && ((b[1] ?? 0) & 0xe0) === 0xe0)) return 'audio/mpeg';
  if (b.length >= 12 && ascii(b, 4, 4) === 'ftyp') {
    const brand = ascii(b, 8, 4);
    if (brand === 'avif' || brand === 'avis') return 'image/avif';
    if (['heic', 'heix', 'mif1', 'msf1', 'hevc'].includes(brand)) return 'image/heic';
    if (brand === 'qt  ') return 'video/quicktime';
    if (brand === 'M4A ' || brand === 'M4B ') return 'audio/mp4';
    return 'video/mp4';
  }
  return null;
}

export function dangerousKind(b: Uint8Array): string | null {
  if (eq(b, 0, [0x4d, 0x5a])) return 'windows_executable';
  if (eq(b, 0, [0x7f, 0x45, 0x4c, 0x46])) return 'elf_executable';
  if (eq(b, 0, [0x50, 0x4b, 0x03, 0x04])) return 'zip_archive';
  if (ascii(b, 0, 4) === 'Rar!') return 'rar_archive';
  if (ascii(b, 0, 4) === '%PDF') return 'pdf';
  if (eq(b, 0, [0xca, 0xfe, 0xba, 0xbe]) || eq(b, 0, [0xcf, 0xfa, 0xed, 0xfe])) return 'mach_o';
  if (ascii(b, 0, 2) === '#!') return 'script';
  const head = ascii(b, 0, Math.min(64, b.length)).trimStart().toLowerCase();
  if (['<!doctype', '<html', '<?xml', '<svg', '<script'].some((p) => head.startsWith(p))) return 'markup';
  return null;
}

const ISO = new Set(['video/mp4', 'audio/mp4', 'video/quicktime']);
const ALIASES: Record<string, string> = { 'image/jpg': 'image/jpeg', 'audio/mp3': 'audio/mpeg', 'audio/x-m4a': 'audio/mp4' };

export function compatible(expected: string, detected: string): boolean {
  const e = ALIASES[expected] ?? expected;
  if (!e || e === 'application/octet-stream' || e === detected) return true;
  return ISO.has(e) && ISO.has(detected);
}

export type VerifyResult = { ok: true; mime: MediaMime } | { ok: false; reason: 'dangerous' | 'not_media' | 'type_mismatch'; detail?: string };

export function verifyHead(head: Uint8Array, expectedMime: string): VerifyResult {
  const danger = dangerousKind(head);
  if (danger) return { ok: false, reason: 'dangerous', detail: danger };
  const mime = sniff(head);
  if (!mime) return { ok: false, reason: 'not_media' };
  if (!compatible(expectedMime, mime)) return { ok: false, reason: 'type_mismatch', detail: `${expectedMime} vs ${mime}` };
  return { ok: true, mime };
}
