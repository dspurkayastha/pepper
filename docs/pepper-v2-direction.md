# Pepper v2: River + Now + Orb, with clinical support

This direction replaces the "Quiet instrument" layout in `ios-app-plan.md` §3–5.
The backend, platform-integration and architecture sections of that plan still
apply. The screens are on the **Pepper v2** page of the *Pepper iOS Design* canvas.

Pepper grows from business manager into **one assistant for your whole day:
clinic, company and life.**

---

## 1. The three ideas

### The River (the backbone)
- Home is a single vertical timeline of today. Past items fade above the NOW line; what's coming sits below it.
- Three **lanes**, each with one colour: **Clinical** (teal), **Company** (slate blue), **Life** (ochre). Filter chips show one lane or all.
- Pinch out for the week, pinch in for an item's detail. Every action Pepper takes is a point on the river, so the river doubles as the audit trail.
- The future is not only your calendar. It includes Pepper's **expectations** ("weekly review: I expect 2 decisions"), and you can decide on those in advance.

### Now cards (the only interruption)
- Anything that needs you becomes **one card** that rises from the Orb over a dimmed river.
- Swipe right for yes, left for later, or hold to talk it through. One card at a time, with a count.
- After the last card, you get a receipt of what Pepper handled on its own, each item with **Undo** (24 h).

### The Orb (reimagined): a drop on the river
- It is not a HUD ring. It is a **small, tactile pebble sitting on the NOW line.** It *is* the present moment.
- **Drag it** to scrub through time. **Hold it** to talk. **Tap it** when it glows to lift the waiting card.
- States: resting (dark, slow breathing) · listening (ripples along the river) · working (a thin arc circles it) ·
  a card for you (warms to ember, a card peeks out) · clinical/private (teal with a lock) · offline (hollow grey).

### Visual language
- Warm paper by day (`#F7F6F2`), with graphite text and hairline rules. The river switches to dark automatically at night and when on call.
- Type: IBM Plex Sans for UI, IBM Plex Mono for times and telemetry, and Bricolage Grotesque only for card headlines.
- Colour carries meaning, not decoration: lane colours, one ember (`#E4572E`) for "needs you", teal for clinical/private.

---

## 2. The clinical module

### What it does
| Capability | How it works |
|---|---|
| **Point-and-shoot capture** | Photo, short video (≤30 s), voice note or document scan from the Capture button, Lock Screen, Action Button or Watch. Pepper suggests which case it belongs to (from the OT list or ward census and the time). |
| **Logbook, drafted for you** | A capture plus a two-line voice note becomes a structured entry: procedure, role, indication, anaesthesia, duration (from timestamps), complications. Pepper asks you to confirm only the fields it couldn't infer. |
| **Supervisor sign-off** | One tap sends entries for sign-off (email/WhatsApp link or the programme's portal). Pepper chases politely before deadlines. |
| **Requirement tracking** | Progress against your programme's numbers (performed / supervised / assisted / emergency), with deadline reminders and export in the university/NMC format. |
| **Dictation to notes** | Ward-round, consult and op notes drafted from dictation into your templates. Handover is compiled from the day's notes. |
| **On-call mode** | During on-call or OT (from roster, calendar or Focus), the river shows only the Clinical lane. Everything else is held until morning. |
| **Thesis and academics** | Guide-meeting prep, chapter comment summaries, literature pulls (PubMed), reference hygiene, conference and CME deadlines. |
| **Teaching file** | Interesting cases (de-identified) tagged for later teaching, presentations or case reports. |
| **CME and credentials** | Registration renewals, CME credit tracking, certificates stored and ready. |

### Privacy by design (not optional)
Patient images are the most sensitive data this app will touch. The rules:

1. **De-identify on the phone, before anything leaves it.** On-device detection blurs faces, ID bands, name boards, monitors with names, and paper charts. EXIF and location are stripped. The capture screen shows what was hidden.
2. **Identifiers stay local.** Hospital numbers and names live only in an encrypted on-device store (Keychain-protected, Face ID gated), linked to entries by a local key. The server and the agent see only de-identified data.
3. **Separate clinical space.** Clinical media and entries sit in their own storage and their own agent, with no memory shared with the business agent. They are never used in content, marketing or product work.
4. **Consent record.** Each capture can attach a consent flag (verbal/written, per your institution's policy). The logbook shows it.
5. **Photos stay out of the camera roll.** Captures go straight into the app's encrypted container, never into Photos or iCloud Photos.
6. **Compliance.** Follow India's DPDP Act 2023 and your institution's clinical photography policy. Confirm the data-retention terms of every AI provider used for clinical data before launch.
7. **Decision support is not diagnosis.** Pepper documents, organises and reminds. It does not make clinical decisions, and the UI never presents it as if it does.

### Data flow (clinical capture)
```
Camera → on-device de-identification → local encrypted store
           │                                  │ (identifiers stay here)
           └─ de-identified media + voice ───→ backend (clinical bucket)
                                               → clinical agent drafts entry
                                               → app shows draft → you confirm
                                               → sign-off request → logbook
```

---

## 3. Updated information architecture

```
Today (the river)           home: all lanes, orb on NOW
  ├─ Now cards              rise from the orb; the only interruption
  ├─ Item detail            any point on the river (thread, files, undo)
  └─ Week / month           pinch out
Capture (always one tap)    photo · video · voice · doc, with privacy shield
Logbook                     entries, requirements, sign-offs, export
Ask                         the dock field + hold-the-orb voice
Settings                    lanes, autonomy per lane, integrations, privacy, memory
Outside the app             Lock Screen capture, Action Button, Watch, widgets, Live Activities
```
The tab bar goes away. The river, the dock (Capture · Ask · Talk) and the Orb are the whole interface.

---

## 4. Features carried forward from the "no constraints" list
Earned autonomy · universal undo · "why did you do that?" · clinic/energy-aware scheduling ·
end-of-day shutdown · weekly 1:1 · relationship memory · camera-to-anything · calls on your behalf ·
advisor panel · pre-mortems. All of these attach to the river as events or cards.

---

## 5. Open questions
1. Specialty and programme: which logbook format and requirement numbers (NMC PG logbook, university e-logbook, other)?
2. Are you a resident, faculty or both? This changes whether sign-off is *requested* or *given*.
3. Hospital policy on clinical photography on personal devices: is there an approved workflow to match?
4. Where do OT lists and rosters come from (HIS, WhatsApp, paper)? This decides how Pepper knows your cases.
5. Which personal areas belong in the Life lane (family calendar, finances, travel, health)?
