# Mobile builds — Android & iOS (Expo EAS)

## 0. One-time setup
```bash
cd mobile
npm install
npm install -g eas-cli
eas login
eas init                       # writes the real projectId into app.json → extra.eas.projectId
```
Then edit `app.json`:
- `ios.bundleIdentifier` and `android.package` → your reverse-domain IDs (e.g. `com.acme.mediaflow`) — **cannot change after the first store release**
- `extra.privacyUrl`, `extra.termsUrl` → where you host the policy pages
- `eas.json` → the API URL for each profile (`EXPO_PUBLIC_API_URL`); production must be `https://`

## 1. Development builds (needed for full functionality)
Expo Go lacks some native configuration (background URLSession, media-library write permissions, custom scheme). Use a dev client:
```bash
eas build --profile development --platform android   # installable APK
eas build --profile development --platform ios       # iOS simulator build
npx expo start --dev-client
```
Or locally with Android Studio / Xcode installed: `npx expo run:android`, `npx expo run:ios`.

Android emulator → backend on your machine: `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`. Physical device → your LAN IP. Plain `http` only works in development builds; release builds refuse non-HTTPS API URLs by design.

## 2. Android
**APK for testers**
```bash
eas build --profile preview --platform android
```
**AAB for Google Play**
```bash
eas build --profile production --platform android
```
**Signing:** on the first build EAS offers to generate an upload keystore and stores it securely. Download a backup with `eas credentials` → Android → Keystore → Download, and keep it in your password manager. Enroll in **Play App Signing** (default for new apps) so Google holds the app-signing key and your upload key can be reset if lost.

Local alternative (no EAS): `npx expo prebuild -p android`, then in `android/`: `./gradlew bundleRelease` with a `signingConfigs.release` block that reads the keystore path/passwords from `~/.gradle/gradle.properties` (never commit them).

**Submit:** `eas submit -p android --profile production` (needs a Play service-account JSON at `secrets/play-service-account.json`; first upload must be done manually in Play Console).

## 3. iOS
Requires an Apple Developer Program membership.
```bash
eas build --profile production --platform ios
```
**Signing:** EAS asks for your Apple ID and creates/reuses the **Distribution certificate** and **App Store provisioning profile** for `ios.bundleIdentifier`. To manage them yourself: `eas credentials` → iOS, or provide a `.p12` + `.mobileprovision`.

Physical-device test builds: register devices with `eas device:create`, then `eas build --profile preview --platform ios` (ad-hoc), or use TestFlight.

**Submit:** `eas submit -p ios --profile production` (set `ascAppId` in `eas.json`), then finish metadata in App Store Connect.

Local alternative: `npx expo prebuild -p ios`, open `ios/*.xcworkspace` in Xcode, set Team + bundle ID, **Product → Archive**, then distribute via Organizer.

## 4. Versioning
`appVersionSource: remote` + `autoIncrement` in the production profile manage `versionCode`/`buildNumber` automatically. Bump the user-visible `version` in `app.json` per release.

## 5. What was verified in this repository
- `npx tsc --noEmit` (strict) passes
- `npx expo export --platform android --platform ios` produces Hermes bundles for both platforms
- `npx expo prebuild` generates both native projects; generated Android permissions are limited to INTERNET, VIBRATE, photo/video media access (and legacy storage for Android ≤ 12); iOS gets only photo-library usage strings

Not verified here (no Apple/Google credentials or devices in the build sandbox): signed builds, installs, store uploads. Follow `docs/TESTING.md` § Device testing.
