import { verifyHead, sniff, dangerousKind } from '../src/lib/fileSignature';
import { safeFileName, uniqueName } from '../src/lib/filenames';
import { formatBytes, formatDuration, formatEta, formatPercent, formatSpeed } from '../src/lib/format';
import { extractUrl, isValidHttpUrl, platformHint } from '../src/lib/url';

const bytes = (...parts: Array<string | number[]>) =>
  new Uint8Array(parts.flatMap((p) => (typeof p === 'string' ? Array.from(p).map((ch) => ch.charCodeAt(0)) : p)));

describe('URL validation & platform detection', () => {
  it('extracts links from shared text', () => {
    expect(extractUrl('wow https://youtu.be/abc?si=1).')).toBe('https://youtu.be/abc?si=1');
    expect(extractUrl('example.com/a.mp4')).toBe('https://example.com/a.mp4');
    expect(extractUrl('hello world')).toBeNull();
    expect(extractUrl('javascript:alert(1)')).toBeNull();
  });
  it('validates', () => {
    expect(isValidHttpUrl('https://vimeo.com/1')).toBe(true);
    expect(isValidHttpUrl('ftp://x.com/a')).toBe(false);
    expect(isValidHttpUrl('https://localhost/x')).toBe(false);
  });
  it.each([
    ['https://m.youtube.com/watch?v=x', 'youtube'], ['https://youtu.be/x', 'youtube'], ['https://www.instagram.com/p/x', 'instagram'],
    ['https://vm.tiktok.com/x', 'tiktok'], ['https://twitter.com/a/status/1', 'x'], ['https://www.pinterest.co.uk/pin/1', 'pinterest'],
    ['https://redd.it/x', 'reddit'], ['https://player.vimeo.com/video/1', 'vimeo'], ['https://tinder.com/x', 'dating'],
    ['https://cdn.example.com/a.mp4', 'web'], ['https://youtube.com.evil.net/watch?v=x', 'web'], ['https://notyoutube.com/', 'web'],
  ])('%s → %s', (url, key) => expect(platformHint(url)).toBe(key));
});

describe('file signature verification (malware-aware saving)', () => {
  it('recognises media', () => {
    expect(sniff(bytes([0xff, 0xd8, 0xff, 0xe0]))).toBe('image/jpeg');
    expect(sniff(bytes([0, 0, 0, 0x20], 'ftypisom'))).toBe('video/mp4');
    expect(sniff(bytes('RIFF', [0, 0, 0, 0], 'WEBP'))).toBe('image/webp');
    expect(sniff(bytes([0x1a, 0x45, 0xdf, 0xa3]))).toBe('video/webm');
  });
  it('rejects executables, archives, HTML error pages and spoofed types', () => {
    expect(dangerousKind(bytes('MZ', [0x90, 0]))).toBe('windows_executable');
    expect(dangerousKind(bytes('PK', [3, 4]))).toBe('zip_archive');
    expect(verifyHead(bytes('  <!DOCTYPE html><html>'), 'video/mp4')).toEqual({ ok: false, reason: 'dangerous', detail: 'markup' });
    expect(verifyHead(bytes([0xff, 0xd8, 0xff, 0xe0]), 'video/mp4')).toMatchObject({ ok: false, reason: 'type_mismatch' });
    expect(verifyHead(bytes('hello world!'), 'image/png')).toEqual({ ok: false, reason: 'not_media' });
    expect(verifyHead(bytes([0, 0, 0, 0x20], 'ftypqt  '), 'video/mp4')).toEqual({ ok: true, mime: 'video/quicktime' });
  });
});

describe('file names', () => {
  it('sanitises', () => {
    expect(safeFileName('../../etc/passwd', 'mp4')).toBe('etc passwd.mp4');
    expect(safeFileName('CON', 'jpg')).toBe('media.jpg');
    expect(safeFileName('a‮gnp.exe', 'png')).toBe('a gnp.exe.png');
    expect(safeFileName('x'.repeat(300), 'mp4').length).toBeLessThanOrEqual(84);
  });
  it('de-duplicates names', () => {
    const taken = new Set(['clip.mp4', 'clip (2).mp4']);
    expect(uniqueName('Clip.mp4', taken)).toBe('Clip (3).mp4');
    expect(uniqueName('new.mp4', taken)).toBe('new.mp4');
  });
});

describe('formatting', () => {
  it('formats sizes, speed, eta, duration, percent', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(5 * 1024 ** 3)).toBe('5.0 GB');
    expect(formatBytes(null)).toBe('—');
    expect(formatSpeed(2 * 1024 * 1024)).toBe('2.0 MB/s');
    expect(formatEta(75)).toBe('1m 15s left');
    expect(formatEta(7300)).toBe('2h 1m left');
    expect(formatDuration(3723)).toBe('1:02:03');
    expect(formatDuration(65)).toBe('1:05');
    expect(formatPercent(50, 200)).toBe('25%');
    expect(formatPercent(50, null)).toBe('');
  });
});
