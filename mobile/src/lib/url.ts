/**
 * Client-side link handling. This is only for instant feedback (e.g. showing a platform badge while
 * typing). The SERVER is authoritative for validation, SSRF checks and platform detection.
 */
const URL_IN_TEXT = /https?:\/\/[^\s<>"'`]+/i;
const BARE_DOMAIN = /^(www\.)?[a-z0-9-]+(\.[a-z0-9-]+)+(\/\S*)?$/i;

export function extractUrl(text: string): string | null {
  const t = (text ?? '').trim();
  if (!t) return null;
  const m = t.match(URL_IN_TEXT);
  if (m) return m[0].replace(/[).,;!?\]}'"]+$/, '');
  if (BARE_DOMAIN.test(t)) return `https://${t}`;
  return null;
}

export function hostOf(url: string): string | null {
  const m = url.match(/^https?:\/\/(?:[^@/?#]*@)?(\[[^\]]+\]|[^/:?#]+)/i);
  return m?.[1] ? m[1].toLowerCase().replace(/\.$/, '') : null;
}

export function isValidHttpUrl(text: string): boolean {
  const u = extractUrl(text);
  if (!u) return false;
  const host = hostOf(u);
  return !!host && (host.includes('.') || host.startsWith('['));
}

const HINTS: Array<[string, string[]]> = [
  ['youtube', ['youtube.com', 'youtu.be', 'youtube-nocookie.com']],
  ['instagram', ['instagram.com', 'instagr.am']],
  ['facebook', ['facebook.com', 'fb.com', 'fb.watch']],
  ['tiktok', ['tiktok.com']],
  ['x', ['x.com', 'twitter.com']],
  ['pinterest', ['pinterest.com', 'pin.it']],
  ['reddit', ['reddit.com', 'redd.it']],
  ['vimeo', ['vimeo.com']],
  ['dating', ['tinder.com', 'gotinder.com', 'bumble.com', 'hinge.co']],
];

function hostMatches(host: string, domain: string): boolean {
  return host === domain || host.endsWith(`.${domain}`);
}

/** Best-guess platform key for UI hints. Look-alike hosts (youtube.com.evil.net) map to 'web'. */
export function platformHint(text: string): string | null {
  const u = extractUrl(text);
  const host = u ? hostOf(u) : null;
  if (!host) return null;
  for (const [key, domains] of HINTS) {
    if (domains.some((d) => hostMatches(host, d) || (key === 'pinterest' && /(^|\.)pinterest\.[a-z.]+$/.test(host)))) {
      return key;
    }
  }
  return 'web';
}

export const PLATFORM_LABELS: Record<string, string> = {
  youtube: 'YouTube',
  instagram: 'Instagram',
  facebook: 'Facebook',
  tiktok: 'TikTok',
  x: 'X',
  pinterest: 'Pinterest',
  reddit: 'Reddit',
  vimeo: 'Vimeo',
  dating: 'Dating app',
  web: 'Website',
};
