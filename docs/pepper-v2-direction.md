# Pepper v2: River + Now + Orb, with clinical support

This direction replaces the "Quiet instrument" layout in `ios-app-plan.md` §3–5.
The backend, platform-integration and architecture sections of that plan still
apply. The screens are on the **Pepper v2** page of the *Pepper iOS Design* canvas.

Pepper grows from business manager into **one assistant for your whole day as a consultant oncosurgeon, founder and family person:
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

### Who it's for
A **consultant surgical oncologist** who also does general surgery, minor procedures and
endoscopy. The clinical module is a **personal case log and practice-outcomes tool**, plus
sign-off for residents' logs. It is not a trainee requirement tracker.

### What it does
| Capability | How it works |
|---|---|
| **OT list intake (WhatsApp + paper)** | Share the WhatsApp message or screenshot to Pepper through the iOS share sheet, or photograph the paper list in Capture's LIST mode. Pepper reads it and matches patients to your OPD notes. It builds tomorrow's list on the river with a prep checklist per case (consent, cross-match, clip marking, lymphoscintigraphy, frozen-section request) and flags gaps. |
| **Point-and-shoot capture** | Photo, video (≤30 s), specimen photo, voice note. Pepper links each capture to the right case using the list and the time. |
| **Case record, drafted** | Oncology fields: diagnosis and site, cTNM/stage (AJCC 8th), neoadjuvant therapy and response, procedure, approach (open/lap/robotic/endoscopic), intent (curative/palliative), your role, time, blood loss, frozen section, intra-op events, resident involved. You confirm only what Pepper couldn't infer. |
| **Histopathology follow-through** | Pending reports are watched. When one arrives (shared photo/PDF), Pepper adds pT, pN, margin status (R0/R1/R2), node yield and ypTNM/TRG after neoadjuvant therapy, then asks you once. |
| **Complications and outcomes** | Clavien-Dindo checks at 30 and 90 days (a one-tap card). Readmissions and re-operations recorded. Practice dashboard: cases by category, R0 rate, median node yield, CD ≥ III rate, length of stay. The same data serves M&M, audit and credentialing. |
| **Tumour board prep** | For each of your patients listed: a one-screen summary (stage, path, imaging, treatment so far, the question for the board), and the decision recorded back into the case. |
| **Surveillance follow-up** | Follow-up schedules by cancer type (e.g. imaging and marker intervals). Reminders are drafted for you or your team to send. Overdue patients are flagged. |
| **Resident logs** | Residents' entries that name you arrive as cards; approve or comment in one swipe. Your own case record can also generate the resident's entry. |
| **Scopy lists** | Biopsy request forms pre-filled. Findings dictated → report draft → biopsy results tracked like histopath. |
| **Dictation to notes** | Ward-round, consult, op notes and discharge summaries drafted from dictation into your templates. Handover compiled at the end of on-call. |
| **Academic** | Case series pulled from your log for papers and talks (de-identified CSV). Literature pulls, CME/conference deadlines, registration renewals. |
| **On-call mode** | During on-call or OT (from the list, calendar or Focus), the river shows only the Clinical lane. Everything else is held until morning. |

### About WhatsApp
WhatsApp has no API for reading personal chats, so Pepper cannot "watch" the OT group.
Instead, reading them takes one gesture: **share the message, screenshot or photo to Pepper** from WhatsApp's share
menu, a Shortcuts automation, or the Capture button. Pepper can also **draft** WhatsApp
messages (to the resident group, OT in-charge or family) for you to send with one tap.

### Privacy by design (not optional)
Patient images are the most sensitive data this app will touch. The rules:

1. **De-identify on the phone, before anything leaves it.** On-device detection blurs faces, ID bands, name boards, monitors with names, and paper charts. EXIF and location are stripped. The capture screen shows what was hidden.
2. **Identifiers stay local.** Hospital numbers and names live only in an encrypted on-device store (Keychain-protected, Face ID gated), linked to entries by a local key. The server and the agent see only de-identified data. Surveillance follow-up needs identity over years, so this store syncs across your own devices end-to-end encrypted (e.g. CloudKit with Advanced Data Protection). It is never readable by the backend.
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

### The Life lane
| Area | What Pepper does |
|---|---|
| **Family calendar** | Merges family calendars. Protects family events against OT and clinic scheduling, and books the cab to get you there. Birthdays and anniversaries come with gift ideas early. |
| **Finances** | EMIs, SIPs, insurance premiums, advance-tax dates, credit-card dues. Checks the balance before auto-debits. Compares renewal quotes. Files invoices and receipts from a photo. Keeps an income view across salary, private practice and the company. |
| **Travel** | CME and conference trips end to end: leave application, flights and hotel holds, visa/passport checks, itinerary on the river. |
| **Plans** | Holidays and family plans, with suggestions when a gap opens up. |
| **Health (yours)** | Check-up reminders, sleep and activity trends from Apple Health on OT-heavy weeks (with permission), and nudges to protect recovery time. |
| **Misc** | Car service, document renewals (passport, licence, registration), home maintenance, subscriptions. |

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

## 5. Decisions so far

### Case templates (build order)
Breast, upper GI, colorectal, HPB, gynae-onc, skin & surface, and sarcoma (selective), plus general surgery, minor procedures and endoscopy. No head & neck, thoracic or uro-onc.
Each template carries staging, site-specific quality fields and a surveillance schedule. The
schedule can be edited per patient.

**Standards used by default** ("whatever is mandated and standard"):
- **Staging:** AJCC TNM, current edition for each site. **FIGO** for gynaecological cancers.
- **Surveillance:** no follow-up schedule is legally mandated in India, so the default is **NCCN** (the most widely followed standard in Indian oncology practice). **ICMR consensus guidelines** are shown alongside where they exist. Your hospital's or tumour board's protocol overrides both when you set it.
- **Complications:** Clavien-Dindo for all cases, plus ISGPS (pancreas) and ISGLS (liver) definitions.
- **Pathology fields:** follow the CAP cancer protocols' core elements, so reports map cleanly.
- **Data protection:** DPDP Act 2023; clinical photography per your institution's policy.

| Template | Site-specific fields |
|---|---|
| **Breast** | ER/PR/HER2, Ki-67 · BCS vs mastectomy · SLNB/ALND · NACT response (RCB / Miller-Payne) · margins · reconstruction |
| **Upper GI** (oesophagus, stomach) | Siewert type · neoadjuvant regimen · lymphadenectomy extent · node yield · TRG · anastomotic leak |
| **Colorectal** | Tumour height · TME quality · CRM · node yield · MMR/MSI · stoma · CEA surveillance |
| **HPB** (pancreas, liver, biliary, gallbladder) | Resection type · vascular resection · ISGPS POPF / DGE / PPH grades · ISGLS liver failure · margins |
| **Gynae-onc** | FIGO stage · PCI · completeness of cytoreduction (CC score) · nodal dissection · HIPEC |
| **Skin & surface** | Melanoma: Breslow depth, ulceration, mitoses, margins, SLNB · non-melanoma skin cancer: subtype, margins, reconstruction/flap |
| **Sarcoma** (selective) | Site, size, depth, FNCLCC grade · margin (R0/R1, planned close) · neoadjuvant RT/chemo · compartment/limb salvage |
| **General & minor** | Procedure, indication, approach, complications (Clavien-Dindo). Deliberately short |
| **Endoscopy** | Scope type, findings, biopsies taken, therapeutic steps, histology follow-through |

### EHR: can't integrate, so capture around it
- Photograph or screenshot the EHR screen, discharge summary or path report. The on-device privacy shield removes names and numbers before anything is read. Then Pepper extracts the fields.
- PDFs you download from the EHR can be shared to Pepper the same way.
- Nothing ever writes back to the EHR. Pepper's notes stay drafts for you to paste in.

### Calendars: Apple + Google (personal)
- **On the phone:** EventKit reads every calendar in iOS Calendar, both iCloud and Google (if the Google account is added in iOS Settings). That covers reading and conflict-checking with no extra login.
- **For the server** (scheduling while your phone is offline, sending invites): Google Calendar via OAuth, token held in the vault. The iCloud calendar is only read and written on the phone.
- The backend only receives what it needs (time, title, lane). Event notes and attendees stay on the phone unless you open an item.

### HDFC Bank: safe by design
Pepper **never holds your net-banking login, never moves money, and never scrapes the bank website.**
- **Read (now):** HDFC's email alerts and monthly e-statements. A Gmail filter labels them, and Pepper reads *only* that label (a narrow Gmail scope), parses debits, credits and balance, and files statements. The statement PDF password lives in the device Keychain.
- **Read (later):** India's RBI **Account Aggregator** network (HDFC is a data provider on it) gives consent-based, read-only, time-limited, revocable access. Receiving that data generally requires being, or going through, a regulated entity, so it's a later option via a regulated partner.
- **Pay:** Pepper prepares the payment (payee, amount, due date) and opens your **HDFC or UPI app** with it pre-filled. *You* authenticate there with your PIN or biometrics. Pepper never gets a payment credential.
- Financial data lives in the Life space. It is encrypted, kept separate from the business and clinical agents, and never used in content.

## 6. Open questions
1. Does your hospital have a clinical photography policy or consent form to match?
