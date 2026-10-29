# Privacy Policy — template

> **Template only.** Replace every `[bracketed]` item, check it against what you actually deploy (analytics, crash reporting, hosting region), and have it reviewed by a lawyer for your jurisdictions (e.g. GDPR, UK GDPR, CCPA/CPRA, India DPDP Act). Host it at the URL set in `app.json → extra.privacyUrl`.

**Effective date:** [date] · **Controller:** [Company legal name], [address] · **Contact:** [privacy@yourdomain.com]

## 1. Summary
MediaFlow Pro lets you save photos and videos you're allowed to keep. Files you download go **directly from the source to your device**; we never store your media on our servers.

## 2. What we collect
| Data | When | Why | Kept for |
|---|---|---|---|
| A random account identifier and session token | first app launch | to operate the service and apply rate limits | until you delete your account; sessions expire after 30 days |
| Email address and password hash | only if you create an account | sign-in across devices | until you delete your account |
| Links you analyze | each analysis | to check what can be downloaded | 15 minutes on our servers |
| Download records (title, source link, quality, file name, size, status) | each download | to show download status | 30 days, or deleted immediately if you turn off "Keep download records on server" |
| Access tokens for platforms you connect (e.g. Vimeo) | only if you connect an account | to fetch your own media from that platform | until you disconnect or delete your account; stored encrypted |
| IP address | each request | security and abuse prevention (rate limiting) | not stored beyond [server log retention, e.g. 14 days] |

We do **not** collect your photos or videos, contacts, location, or advertising identifiers, and we don't sell or share personal data for advertising.

## 3. On your device
Download history, settings and downloaded files stay on your device. You can clear history or turn it off in Settings, and delete files at any time.

## 4. Permissions
- **Photos / media library:** only to save files you choose to download.
- **Network:** to analyze links and download files.

## 5. Third parties
When you analyze a link, our server contacts that link's website or platform to read publicly available metadata, or (if you connected an account) that platform's official API on your behalf. Those services' own privacy policies apply to them. Our infrastructure providers: [hosting provider, database provider].

## 6. Your rights
You can access, export or delete your data. In the app: **Settings → Delete my account and server data** deletes everything we hold about you immediately (backups roll off within [30] days). Or email [privacy@yourdomain.com]. [Add jurisdiction-specific rights and supervisory-authority contact.]

## 7. Security
HTTPS for all traffic, hashed passwords (Argon2id), hashed session tokens, encrypted platform tokens, minimal retention.

## 8. Children
Not directed to children under [13/16]. [Adjust per jurisdiction.]

## 9. Changes
We'll post updates here and change the effective date; material changes will be notified in the app.
