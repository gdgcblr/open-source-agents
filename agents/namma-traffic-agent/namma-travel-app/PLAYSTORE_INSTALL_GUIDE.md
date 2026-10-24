# 📱 Namma Travel App - Play Store & App Store Installation & Publishing Guide

> **Namma Bengaluru Travel App** (`com.nammatraffic.travelapp`)  
> Cross-platform mobile commute optimizer for Android (Google Play Store) and iPhone (Apple App Store / iOS PWA).

---

## 🌟 Table of Contents
1. [Instant Device Testing (Zero Friction)](#1-instant-device-testing-zero-friction)
   - [Android (1-Tap WebAPK Install)](#android-chrome--samsung-internet)
   - [iPhone / iPad (Apple Home Screen App)](#iphone--ipad-apple-safari)
2. [Google Play Store: Step-by-Step Build & Publish](#2-google-play-store-step-by-step-build--publish)
   - [Method A: Google Bubblewrap CLI (Recommended TWA)](#method-a-google-bubblewrap-cli-recommended-twa)
   - [Method B: Capacitor Android Studio Project](#method-b-capacitor-android-studio-project)
   - [Publishing to Google Play Console](#publishing-to-google-play-console)
3. [Apple App Store (iOS): Step-by-Step Build & Publish](#3-apple-app-store-ios-step-by-step-build--publish)
   - [Capacitor iOS Xcode Project](#capacitor-ios-xcode-project)
   - [Submitting to TestFlight & App Store Connect](#submitting-to-testflight--app-store-connect)
4. [How Users Download & Install From Google Play Store](#4-how-users-download--install-from-google-play-store)
5. [Project Architecture & Config Reference](#5-project-architecture--config-reference)

---

## 1. Instant Device Testing (Zero Friction)

Before submitting to app stores, test the live mobile experience directly on any phone:

### Android (Chrome / Samsung Internet)
1. Open Google Chrome on your Android phone and navigate to:
   ```text
   http://<YOUR_LOCAL_IP>:8000/
   ```
2. Chrome automatically detects the Web App Manifest and Service Worker:
   - A banner will appear at the bottom: **"Add Namma Travel App to Home screen"**.
   - Or tap the 3-dots menu **(⋮)** in Chrome and tap **"Install App"** (or **"Add to Home screen"**).
3. Tap **Install**.
4. Android compiles a lightweight native **WebAPK**:
   - The app appears with the Namma Traffic app icon on your home screen and app drawer.
   - It launches full-screen (standalone mode) without browser address bars.
   - It supports offline caching and native app shortcuts.

### iPhone / iPad (Apple Safari)
1. Open Safari on iOS and browse to the web app URL.
2. Tap the **Share** button (box with upward arrow $\uparrow$ at the bottom of Safari).
3. Scroll down and tap **"Add to Home Screen"**.
4. Tap **Add** in the top-right corner.
5. The Namma Travel App icon appears on your iOS Home Screen and in the iOS App Library:
   - Runs in native standalone mode (`apple-mobile-web-app-capable`).
   - Uses native iOS bottom sheet ergonomics and respects the iPhone notch / dynamic island (`viewport-fit=cover`).

---

## 2. Google Play Store: Step-by-Step Build & Publish

Google Play officially accepts PWAs via **Trusted Web Activities (TWA)** and native wrappers like **Capacitor**.

### Method A: Google Bubblewrap CLI (Recommended TWA)
Google Bubblewrap is the official CLI built by the Google Chrome team to convert web apps into signed Android App Bundles (`.aab`) ready for the Play Store.

#### Step 1: Install Prerequisites
Ensure Node.js (>= 18), Java JDK 17, and Android SDK command-line tools are installed:
```bash
npm install -g @bubblewrap/cli
```

#### Step 2: Initialize Bubblewrap using our Pre-configured Manifest
```bash
cd namma-travel-app
bubblewrap init --manifest=http://localhost:8000/manifest.json
```
Bubblewrap reads the manifest and sets:
- **Package ID:** `com.nammatraffic.travelapp`
- **App Name:** `Namma Travel App`
- **Theme Color:** `#1a73e8`
- **Splash Screen Color:** `#0f172a`

#### Step 3: Build the Production Android App Bundle (.aab)
```bash
bubblewrap build
```
During the first build, Bubblewrap will create a signing keystore (`android.keystore`) and prompt for a password. It outputs:
- `app-release-bundle.aab` (Ready for Google Play Store upload)
- `app-release-signed.apk` (For direct sideload testing via `adb install`)

---

### Method B: Capacitor Android Studio Project
For full access to native Android SDKs and plugins:

#### Step 1: Install Dependencies & Initialize Android Platform
```bash
cd namma-travel-app
npm install
npx cap add android
npx cap sync
```

#### Step 2: Open in Android Studio
```bash
npx cap open android
```

#### Step 3: Generate Signed Bundle in Android Studio
1. In Android Studio, go to menu: **Build** $\rightarrow$ **Generate Signed Bundle / APK...**
2. Choose **Android App Bundle** and click **Next**.
3. Select your release keystore (or click **Create new...**).
4. Select destination folder and build variant **release**.
5. Click **Finish**. Android Studio generates `app-release.aab`.

---

### Publishing to Google Play Console

1. **Log in to Google Play Console:**
   - Go to [play.google.com/console](https://play.google.com/console).
   - If you don't have a Google Play Developer Account, register ($25 one-time registration fee).

2. **Create New App:**
   - Click **Create App**.
   - **App name:** `Namma Travel App`
   - **Default language:** `English (India)`
   - **App or game:** `App`
   - **Free or paid:** `Free`
   - Accept the Developer Program Policies and click **Create app**.

3. **Complete Store Listing (App Details):**
   - **Short description:** *AI-powered Bengaluru commute optimizer with live metro, BMTC buses, and cab fare saver.*
   - **Full description:**  
     *Namma Travel App is Bengaluru's dedicated multimodal transit copilot. Compare BMTC Ordinary vs Vajra AC buses, explore Purple, Green & Yellow Metro lines with fare charts and transfer alerts, monitor active BBMP/BMRCL road repair zones, and compare Cab vs Auto vs Bike Taxi fares to save money and beat Bengaluru traffic.*
   - **App Icon:** Upload `icon-512.svg` (or 512x512 PNG).
   - **Screenshots:** Upload at least 2 phone screenshots (e.g. Map Route with Live Bus & Metro tracking).

4. **Digital Asset Links (TWA Verification):**
   - For Bubblewrap TWA, Google verifies ownership between the app and domain.
   - Upload the generated `assetlinks.json` to:
     `https://<your-domain>/.well-known/assetlinks.json`

5. **Upload the Bundle (.aab):**
   - In Google Play Console, go to **Release** $\rightarrow$ **Production** (or **Internal Testing**).
   - Click **Create new release**.
   - Drag and drop `app-release-bundle.aab`.
   - Add release notes (e.g. *Initial release of Namma Travel App v1.0.0*).
   - Click **Save** $\rightarrow$ **Review release** $\rightarrow$ **Start rollout to Production**.

6. **Review & Approval:**
   - Google typically reviews new apps within 24 to 72 hours. Once approved, the status changes to **Available on Google Play**.

---

## 3. Apple App Store (iOS): Step-by-Step Build & Publish

### Capacitor iOS Xcode Project

#### Step 1: Initialize iOS Platform
*(Requires macOS with Xcode installed)*
```bash
cd namma-travel-app
npm install
npx cap add ios
npx cap sync
```

#### Step 2: Open in Xcode
```bash
npx cap open ios
```

#### Step 3: Configure Signing & Capabilities
1. In Xcode, select the **App** project in the left navigator.
2. Under **Signing & Capabilities**:
   - Check **Automatically manage signing**.
   - Select your **Apple Developer Team**.
   - Bundle Identifier will be `com.nammatraffic.travelapp`.
3. Under **General**, verify App Name, Deployment Target (iOS 14.0+), and Display Orientation (Portrait).

---

### Submitting to TestFlight & App Store Connect

1. In Xcode menu: **Product** $\rightarrow$ **Archive**.
2. Once archiving completes, the Xcode Organizer window opens.
3. Click **Distribute App** $\rightarrow$ **App Store Connect** $\rightarrow$ **Upload**.
4. Log into [appstoreconnect.apple.com](https://appstoreconnect.apple.com):
   - Your build will appear under **TestFlight** within ~15 minutes for internal/external beta testers.
   - Fill in app privacy details, category (*Navigation / Travel*), screenshots, and description.
   - Select the uploaded build and click **Submit for Review**.

---

## 4. How Users Download & Install From Google Play Store

Once published, users can install Namma Travel App using these simple steps:

1. **Direct Play Store URL:**
   - Provide users with your unique app link:
     ```text
     https://play.google.com/store/apps/details?id=com.nammatraffic.travelapp
     ```
2. **Search in Google Play Store:**
   - Open the **Google Play Store** app on any Android device.
   - In the search bar, type `Namma Travel App` or `Namma Bengaluru Traffic`.
   - Locate the app with the Namma Traffic transit icon.
3. **One-Tap Install:**
   - Tap **Install**.
   - The Play Store automatically downloads and verifies the package.
   - The app icon is added to the home screen.
4. **Automatic Updates:**
   - Any new transit updates, bus routes, or metro line additions deployed to the web automatically propagate to users without requiring manual app updates!

---

## 5. Project Architecture & Config Reference

```text
namma-travel-app/
├── package.json              # NPM configuration with Capacitor & Bubblewrap tooling
├── capacitor.config.json     # Native app configuration (App ID, App Name, splash, status bar)
├── twa-manifest.json         # Google Trusted Web Activity config for Play Store bundling
├── PLAYSTORE_INSTALL_GUIDE.md# This comprehensive installation & release guide
├── README.md                 # Project summary and developer instructions
└── www/                      # Production mobile web bundle
    ├── index.html            # Responsive mobile layout with touch bottom sheet & route map
    ├── manifest.json         # W3C Web App Manifest (portrait, standalone, theme colors)
    ├── sw.js                 # Service worker providing offline transit route cache
    ├── icon-192.svg          # 192x192 vector app icon for mobile launchers
    └── icon-512.svg          # 512x512 splash screen & high-DPI maskable icon
```

### Key Configurations Summary:
- **Application ID:** `com.nammatraffic.travelapp`
- **Application Name:** `Namma Travel App`
- **Theme Color:** `#1A73E8` (Google Material Blue)
- **Background Color:** `#0F172A` (Slate Dark)
- **Supported Platforms:** Android (Play Store + PWA) & iOS (App Store + Safari PWA)
