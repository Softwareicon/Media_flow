# Store submission checklists

Downloader apps get extra scrutiny on both stores. The design choices that matter most: YouTube/TikTok are link-only, nothing bypasses logins or DRM, and every non-downloadable result explains why.

## Google Play

**Policy**
- [ ] Listing does **not** use YouTube/Instagram/TikTok etc. names or logos in the app title, icon, screenshots or keywords (Impersonation & IP policy). Say "save photos and videos you own or have permission to keep".
- [ ] No feature downloads YouTube content (Play rejects apps that help violate another service's terms). Verify `/platforms` in the release backend shows YouTube as `link_only`.
- [ ] Only platforms you hold approved API access for are configured on the production backend.
- [ ] Content rating questionnaire completed (users can open arbitrary web media → answer honestly about user-generated content).
- [ ] Target API level meets the current Play requirement (Expo SDK 58 default).

**Data safety form** (matches the privacy policy template)
- [ ] Data collected: email address (optional, account management), app activity — download records (optional, can be turned off), app info & performance (crash logs, if you add them)
- [ ] Data encrypted in transit: yes. Users can request deletion: yes (in-app *Delete my account*)
- [ ] Data shared with third parties: no (OAuth tokens are used only to call that platform on the user's behalf)
- [ ] Photos/videos: accessed only to *save* files; not collected

**Permissions**
- [ ] Only INTERNET, VIBRATE, READ_MEDIA_IMAGES/VIDEO (+ legacy storage ≤ Android 12). Justify media permissions as "saving downloaded files to the user's gallery".
- [ ] Account deletion link provided in Play Console (in-app path: Settings → Delete my account and server data; also host a web form or email address)

**Release**
- [ ] AAB signed with upload key, Play App Signing enrolled
- [ ] Internal testing track → closed testing (new personal developer accounts must run a closed test with testers for the required period before production)
- [ ] Screenshots: phone + 7" and 10" tablet; feature graphic 1024×500
- [ ] Privacy policy URL live and reachable

## Apple App Store

**Guidelines to address**
- [ ] **5.2.3 (Audio/Video downloading):** app must not facilitate saving third-party media without authorization. In *App Review notes* explain: downloads come only from public direct files and from the user's own connected accounts; YouTube/TikTok open in their apps; include a demo account and a test link to a sample file you host.
- [ ] **5.1.1(v) Account deletion:** accounts can be created in-app, so in-app deletion exists (Settings → Delete my account and server data).
- [ ] **4.8 Sign in with Apple:** not required — the app has no third-party *login*; platform connections are content authorizations, not sign-in. Re-check if you add social login.
- [ ] No platform logos/trademarks in the icon or screenshots.

**App Privacy ("nutrition label")**
- [ ] Contact info → email (optional, app functionality, linked to user)
- [ ] Usage data → download records (optional, app functionality, linked to user)
- [ ] Not used for tracking; no ATT prompt needed (no ad SDKs)
- [ ] `ITSAppUsesNonExemptEncryption = false` is set (standard HTTPS only)

**Build & metadata**
- [ ] Bundle ID registered, distribution certificate + App Store profile (EAS-managed)
- [ ] `NSPhotoLibraryAddUsageDescription` text is specific (present in app.json)
- [ ] Screenshots: 6.9" and 6.5" iPhone, 13" iPad (app supports tablets)
- [ ] Age rating questionnaire (unrestricted web access → likely 17+ unless you restrict to connected accounts)
- [ ] Support URL, privacy policy URL, review demo account
- [ ] TestFlight external test round before submission
