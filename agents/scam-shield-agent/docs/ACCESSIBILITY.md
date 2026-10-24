# Scam Shield: App and Accessibility Results

Tested on 2026-10-24 on Windows 11 with headless Chrome 155, driven over the
DevTools protocol by a test script (not committed). The server ran locally **without a Gemini key**, so the second result
comes from the server's rule engine ("Checked with built-in rules") and not from the AI.

Status key: **pass** = tested and passed · **fixed, not re-tested** = a problem was found and fixed, but the
test was not run again (we ran out of time) · **untested** = not run · **phone** = needs a real phone (steps below).

## Results

| # | Item | Status | Evidence |
|---|---|---|---|
| E1 | Offline result first, then the server result | pass (rules mode) | The offline verdict "⛔ Scam" appears immediately with "Quick offline check…", then "Checked with built-in rules · 0.01s". Focus moves to the verdict heading. **The AI result itself is untested** because the test used no key. |
| E2 | Works offline after the first load | untested | In headless Chrome the service worker did not take control of the page during the test, so we could not reload it offline. Needs a manual check (steps below). |
| E3 | Usable on Slow 3G | pass | Throttled to 2000 ms round trip at 400 kbit/s with the cache off: 16,820 bytes transferred, first paint after 2,280 ms, page loaded after 2,378 ms. The offline verdict appeared 48 ms after tapping Check, and the server result after 2,188 ms. |
| E4 | Screenshot shrunk to about 150 KB or less | pass | A 24.1 MB PNG became a 117.5 KB image (request 156.8 KB). A 1.6 MB JPEG became 89.2 KB (request 119.0 KB). |
| E5 | Voice input | phone | See steps below. |
| E6 | Read aloud and auto-read | phone | See steps below. |
| E7 | Language switch updates everything and is remembered | pass | After switching to Kannada, all 19 labelled elements and the placeholder match the Kannada strings. The choice is still set after a reload, and the verdict, warning signs and mode line all appear in Kannada. |
| E8 | Install to home screen | phone | The manifest has a name, `display: standalone`, an icon and `start_url`. Lighthouse Best Practices scored 100. |
| E9 | Share from WhatsApp or SMS | phone | Desktop simulation passed: opening `/?title=Fwd&text=<scam>` filled the message box, ran a check ("⛔ Scam") and cleaned the URL back to `/`. The real Android share sheet is untested. |
| E10 | Errors show a clear message plus the offline result | pass | Server unreachable, and server answering 429: both show "Could not reach the AI. Showing the offline check." with the offline verdict. With a screenshot only and the server down, the browser's raw text "Failed to fetch" is shown (minor; see notes). |
| E11 | Keyboard only | partly tested | Tab order is skip link > language > settings > message > Speak > Screenshot > Check > help link. The skip link is visible on focus and jumps to the message box. Focus moves to the verdict after a check. Opening settings with Enter and toggling with Space were **not verified**: the test's key events were faulty, and the run was stopped. |
| E12 | Focus outline always visible | fixed, not re-tested | Every tab stop showed a 4 px outline **except the Screenshot button**: the outline was drawn on the hidden 1 px file input. Fix: the visible Screenshot button now gets the outline when the hidden input is focused (CSS `label.btn:has(+input:focus-visible)`). |
| E13 | Screen reader announces the verdict | phone | Inspection only: the status line is `role=status aria-live=polite`, and after a check focus moves to the verdict heading (`tabindex=-1`), so the heading should be read out. |
| E14 | Verdict shown by icon and word, not colour alone | pass | The heading reads "⛔ Scam" / "⚠️ Be careful" / "✅ Looks safe", with the risk shown as text ("Risk: 72/100"). |
| E15 | Touch targets at least 48 px | fixed, not re-tested | All buttons, the select box, the settings summary, the text box and the Screenshot button are ≥ 48 px. Two were smaller: the skip link (24 px tall) and the cybercrime.gov.in link (21 px). Both now have a 48 px minimum height. |
| E16 | Large text at 320 px wide with no sideways scrolling | pass | Root font is 20 px; scroll width equals 320 px in English, Tamil and Malayalam, with the verdict shown. |
| E17 | High contrast passes contrast checks | fixed, not re-tested | 81 text elements were measured for each of the 3 verdicts. All were at least 4.5:1 **except the skip link** (browser default blue on black, 2.23:1). The skip link now uses the page text colour. |
| E18 | Dark mode readable | fixed, not re-tested | Same result as E17 (skip link 1.97:1 on dark). Same fix. |
| E19 | Reduced motion respected | pass | Spinner animation `s` normally; with reduced motion set, there is no animation and no spinner. |
| E20 | Different vibration per verdict | phone | Code: scam = 3 long pulses, careful = 2 medium, safe = 1 short. |
| E21 | `<html lang>` follows the language | pass | It is `kn` after switching and after a reload. |
| E22 | Lighthouse accessibility score | pass | Lighthouse 13.5.0 (headless Chrome 155): **Accessibility 100, Best Practices 100**. Measured after the translation fixes, before the 3 small CSS fixes above. |
| E23 | All 8 languages have every key | pass | Checked by a script that compares the keys of every language. |
| E24 | Translation review | pass | Sub-agent review found 4 high, 9 medium and 4 low issues; all 26 string changes were applied (see below). Not checked by a native speaker. |
| E25 | Under 20 KB gzipped | pass | `gzip -9 -c static/index.html \| wc -c` gives 16,551 bytes. |
| E26 | No external scripts, fonts or trackers | pass | Previously verified. The only external URL is the cybercrime.gov.in link. |
| E27 | This file | pass | |

After the changes, the shared rule test still passes: `node tests/test_offline_rules.js` reports 20/20. The offline-rules block was not changed.

## Translation fixes (E24)

High: Kannada and Marathi "Remove screenshot" read as "take screenshot" (now ತೆಗೆದುಹಾಕಿ / हटवा). Kannada and Telugu
"Looks safe" said "is safe" (now ಸುರಕ್ಷಿತವಾಗಿ ಕಾಣುತ್ತದೆ / సురక్షితంగా అనిపిస్తోంది).
Medium: Hindi uses one word for scam (धोखाधड़ी) in both the verdict and "Lost money" line. Polite button forms are now consistent in Tamil, Telugu, Kannada and Bengali.
Tamil now uses the everyday words for link, app and contrast. Kannada and Malayalam "Accessibility settings" now use plain words ("easy use").
Low: The Tamil and Kannada tagline grammar is fixed, Marathi राहा is spelled correctly, and the Telugu "rules" line is less bookish.

## Steps for a real phone (Android, Chrome)

Start the server on your PC (`python server.py`) and open `http://<PC-IP>:8080` on the phone (same Wi-Fi).
Note: voice, install and share need HTTPS or localhost. Either use `chrome://flags` → "Insecure origins treated as
secure" → add `http://<PC-IP>:8080`, or forward the port over USB with `chrome://inspect` → Port forwarding, then open `localhost:8080`.

1. **E5 Voice:** Tap 🎤 Speak and allow the microphone. Say "Your account will be blocked, share OTP". The text should appear in the box. Repeat once in Hindi with the language set to हिन्दी.
2. **E6 Read aloud:** Check a message, then tap 🔊 Read aloud; you should hear the verdict. Turn on Settings → "Read result aloud automatically", check again, and it should speak without a tap.
3. **E8 Install:** Chrome menu ⋮ → "Install app" / "Add to Home screen". It should open from the home screen with no browser bar.
4. **E9 Share:** After installing, long-press a message in WhatsApp or SMS → Share → Scam Shield. The app should open with the text filled in and a verdict shown.
5. **E13 Screen reader:** Turn on TalkBack. Check a message; TalkBack should read the verdict ("Scam" / "Be careful" / "Looks safe").
6. **E20 Vibration:** Check a scam message (3 long buzzes), a "be careful" one (2) and a safe one (1 short).
7. **E2 Offline (can also be done on a PC):** Load the page once, turn on airplane mode, reload. The page should still open, and a check should show "You are offline…" with a verdict.

## Notes and open items

- **Re-test after the CSS fixes** (E12, E15, E17, E18): Tab to the Screenshot button and you should see an orange outline. Tab once on a fresh page to see the skip link.
- **E2 is untested;** please do step 7 above.
- **E1 with real Gemini is untested** (no key used, to save free-tier quota).
- Minor, not fixed: when only a screenshot is sent and the server is unreachable, the status shows the browser's English text "Failed to fetch" rather than a translated message.
