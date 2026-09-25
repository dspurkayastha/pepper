# Pepper for iOS: Product, Design & Build Plan

> **Update:** the chosen direction is now **Pepper v2: River + Now + Orb, with
> clinical support**. See [`pepper-v2-direction.md`](pepper-v2-direction.md). It
> supersedes the layout and visual design in §3–5 below. The rest of this plan
> still applies.

> Pepper is a calm, always-on chief of staff for SciScribe Solutions. It keeps five
> products running, talks when you want to talk, and interrupts only when a
> decision is really yours.

This plan covers the full iOS app. It builds on the backend relay in `backend/`
and the Managed Agents setup it uses. The visual design is on the
**Pepper iOS Design** canvas, which has 6 core screens plus the design language.
This document is the written spec behind it.

---

## 1. What an app like this can do for you

The current backend covers chat, a weekly routine, escalations and a product list.
With the full app, Pepper can also do the following.

### Run the business (operations)
- **Daily brief.** A 60–90 second spoken or written summary at 9:00 IST. It covers what broke overnight, what Pepper fixed, what is due today and what needs your call.
- **Incident response.** An uptime alert or failed deploy starts a session automatically. Pepper looks into it, tries the safe fix (restart a service, roll back a Vercel deploy), and asks you before doing anything risky.
- **Renewals and expiry watch.** Domains, SSL certificates, API keys, Apple certificates and cloud credits. It warns you 30, 7 and 1 days ahead, and can renew with one tap.
- **Backup verification.** It restores the latest backup to a scratch database each week and reports the result, instead of only checking that the file exists.
- **Cost watch.** Hetzner, Oracle, Vercel and Anthropic spend, with alerts when something jumps.
- **Release manager.** Summarise open PRs per product, write changelogs, tag releases and post release notes.

### Grow the business
- **Content engine.** The weekly LinkedIn/X batch, written in your voice (kept in memory). You approve or edit it in the app, then it gets scheduled.
- **Lead and inbox triage.** Sort SciScribe enquiries, draft replies and flag hot leads. Manuscript-editing quotes can be generated from a template.
- **Pilot tracking.** Aakhyan pilot metrics (discharge summaries sent, delivery failures, language mix), turned into a weekly note for hospital partners.
- **Grant, tender and conference radar.** A weekly scan for relevant calls in health AI and clinical research tools, each summarised with deadlines.
- **Competitive watch.** Monthly notes on competitors to Scribe EDC and Synthesi.se.

### Run your day
- **Calendar and prep.** Meeting briefs 15 minutes before a call: who the person is, the last emails, open items.
- **Voice capture.** "Pepper, remind me to…" or "note that the Apollo pricing should…" is filed into the right product's memory or task list.
- **Share-to-Pepper.** Send any link, PDF, screenshot or email from the iOS share sheet ("summarise", "turn into a task", "reply to this").
- **Document work.** Draft proposals, SOWs, investor updates and grant sections. Outputs appear as files in the app.
- **Research on demand.** Literature scans and systematic-review scoping. These fit your field and Synthesi.se.

### Be present everywhere on iOS
- **Siri and the Action Button.** Hold to talk to Pepper from anywhere.
- **Lock Screen Live Activities.** Watch a running task ("Weekly report: checking backups, 3/6").
- **Widgets.** Pending decisions, system health and the next scheduled routine.
- **Actionable notifications.** Approve or decline straight from the notification. Risky approvals need Face ID.
- **Apple Watch.** Raise to speak, tap to approve, plus a haptic when something needs you.
- **Focus-aware.** Only blocking decisions come through during a "Clinic" or "Deep Work" Focus.

### Control and trust
- **Autonomy dial per area.** Read-only, act and tell me, or ask first. Separate settings for infra, content, email and money.
- **Full audit trail.** Every action Pepper took, with the tool call, when it happened and what it cost.
- **Memory you can see and edit.** What Pepper knows about you, each product and past decisions.
- **Budgets.** Hard caps per task and per week.

---

## 2. Product principles (the "Jarvis" qualities)

| Quality | What it means in the app |
|---|---|
| **Present, not loud** | A single presence indicator (the Orb) shows Pepper's state at all times. No badges on everything, no feeds to scroll. |
| **Anticipates** | Home is a *brief*, not an inbox. Pepper tells you what matters before you ask. |
| **Brief by default** | Every screen leads with the one-line answer. Detail is one tap away, never in the way. |
| **Shows its work** | Tool activity is visible, compact and expandable. You can always see *what* Pepper did. |
| **Asks only when it matters** | Decisions are rare, structured and one-tap. Everything reversible happens without asking. |
| **Voice-first, touch-complete** | Anything you can say you can also tap, and the other way round. |
| **Calm technology** | Dark-first, restrained motion, precise typography. The design should feel expensive because it is quiet. |

---

## 3. Information architecture

```
Tab bar (Liquid Glass, floating)
├── Brief        home: greeting, morning brief, vitals, needs-you, in-progress
├── Threads      conversations with Pepper (sessions), searchable
├── ◉ Talk       centre button: full-screen voice mode (also long-press anywhere)
├── Decisions    escalations + tool approvals, with history
└── Systems      products, infrastructure, renewals, spend
Settings (from avatar)
├── Integrations   connect GitHub, Gmail, Calendar, servers… (vault-backed)
├── Routines       scheduled deployments (Mon plan / Wed content / Fri review / custom)
├── Memory         view/edit what Pepper remembers
├── Autonomy       per-area permission dial
├── Budgets & usage
├── Voice          voice, speed, language (English / Hindi / Bengali)
└── Security       devices, passkeys, Face ID rules, audit log
Outside the app
├── Siri / App Intents / Action Button / Control Center control
├── Widgets (Home + Lock Screen + StandBy)
├── Live Activities (Dynamic Island + Lock Screen)
├── Notifications with actions
├── Share extension
└── Apple Watch app + complication
```

---

## 4. Screen specs

### 4.1 Brief (home)
- **Header:** the Orb (small) + "Good morning, Dev." + a mono status line: `WED 24 SEP · 09:02 IST · ALL SYSTEMS NOMINAL`.
- **Morning brief card:** 3–5 lines with a ▶ *Play brief* button (spoken, about 90 s). Tap a line to open its thread.
- **Vitals row:** 3 tiles (Uptime x/5, Decisions pending, Spend this week). Tap to open Systems or Decisions.
- **Needs you:** up to 3 decision rows (amber dot, title, category, age). "See all" opens Decisions.
- **In progress:** running sessions, each with a small progress ring and its current step.
- **Empty state:** "Nothing needs you. Pepper is watching 5 products." plus the next routine time.
- **Pull to refresh** asks for a fresh brief. The pull animates the Orb.

### 4.2 Talk (voice mode)
- Full-screen, black. The large Orb reacts to voice level (listening) and to thinking or speaking.
- A live transcript (your words) fades into Pepper's reply as it streams. Chips show tool activity ("UptimeRobot ✓").
- Controls: **hold-to-talk** or tap-to-toggle, cancel, switch to keyboard. Speaking over Pepper cuts it off (barge-in).
- Transcription is on-device (Speech framework, SpeechAnalyzer). Pepper's replies are spoken with a streaming TTS voice.
- Every voice exchange is saved as a thread.

### 4.3 Threads + thread detail
- The list shows title (auto-named), last line, product tag and cost. Search runs across all threads.
- In detail, your messages sit right-aligned in quiet bubbles. Pepper's replies are full-width text, not bubbles, so they read like a document.
- **Activity block:** "Ran 4 steps" collapses by default. Expanded, it shows each tool (github, bash, write…) with a status and duration.
- **Files card:** outputs (`weekly_plan.md`, `content_batch.docx`) open in Quick Look and can be shared.
- **Composer:** text field, attach (photo/file/link), mic. Messages queue while Pepper is working.
- **Resume:** reopening a thread reconnects the stream and replays missed events (see §8).

### 4.4 Decisions
- **List:** pending first. Blocking ones are pinned with an amber `BLOCKING` tag. Resolved history sits below.
- **Detail:** category, the question in one sentence, context (collapsible), **options as selectable cards**, Pepper's **recommendation** marked on its card, and a preview of what will happen (e.g. the 7 posts).
- **Actions:** Approve (primary), Edit & approve, Decline with a note. Any action in the *risky* class needs Face ID.
- **Tool approvals** (from permission policies) use the same card. It shows the tool, the target and a diff or command preview.

### 4.5 Systems
- **Products:** one row per product with status pill, priority, a 7-day uptime sparkline and p95 latency. Tapping a row opens product detail: deploys, open PRs, errors, the product's memory notes, and "Ask Pepper about this product".
- **Infrastructure:** Oracle, Hetzner and Vercel with CPU, disk and last backup.
- **Renewals:** domains, certificates and keys sorted by days left.
- **Spend:** this week vs last, split by provider and by Pepper task.

### 4.6 Settings screens
- **Integrations:** a card per service showing connected/not connected, scopes and last used. "Connect" runs OAuth through the backend into the vault. The phone never holds the secret.
- **Routines:** each scheduled deployment with its cron in plain English ("Mondays 9:00 IST"), pause/resume, "Run now", run history and a rubric editor.
- **Memory:** a tree of memory documents (`/profile.md`, `/products/aakhyan.md`, `/decisions/2026-09.md`). Documents can be edited, and versions viewed and restored.
- **Autonomy:** per area (Infra, Content, Email, Money, Code), a 3-step control: Observe / Act & tell / Ask first.

---

## 5. Design language

### 5.1 Direction
**"Quiet instrument."** A near-black ground, hairline structure, precise mono telemetry
and one luminous accent for Pepper herself. It borrows from avionics and good
watch faces, not sci-fi holograms. No gradient washes, neon glows or fake HUD clutter.
Glow is used once: the Orb.

### 5.2 Colour tokens (dark-first; light mode mirrors the roles)

| Token | Dark | Role |
|---|---|---|
| `bg.void` | `#07090C` | App background |
| `bg.surface1` | `#0E1217` | Cards |
| `bg.surface2` | `#151A21` | Raised / pressed, user bubbles |
| `line.hairline` | `#1E252E` | Borders, dividers (1 px) |
| `text.primary` | `#E8EEF4` | Primary text |
| `text.secondary` | `#9AA7B4` | Body secondary |
| `text.tertiary` | `#7A8694` | Mono labels, captions (≥4.5:1 on void) |
| `accent.arc` | `#5FD3F3` | Pepper, primary actions, "nominal" |
| `signal.amber` | `#F5A524` | Needs you, blocking |
| `signal.critical` | `#FF6B5E` | Down / failed (always with a text label) |
| `on.accent` | `#051017` | Text on arc/amber fills |

Status is never shown by colour alone. Every dot has a word next to it (Nominal, Degraded, Down).

### 5.3 Typography
- **App:** SF Pro (Display/Text) for UI, **SF Mono** for telemetry, labels, timestamps, costs and IDs.
- **Mockups:** Geist + Geist Mono stand in for SF, which can't be embedded on the web.
- **Scale:** Large title 32/38 light · Title 22/28 medium · Headline 17/22 semibold · Body 16/22 · Callout 15/20 · Mono label 11/14 medium, +8% tracking, UPPERCASE · Caption 12/16.
- All sizes map to Dynamic Type styles. Layouts reflow up to AX5.

### 5.4 Space, shape and material
- 4 pt base grid. Screen gutters are 20 pt. Cards use 16 pt padding and sit 12 pt apart.
- Radii: cards 20, rows 14, chips and pills fully rounded, buttons 14.
- **Liquid Glass** (iOS 26 system material) only on the floating tab bar, the navigation bar and the Talk overlay. Content cards stay solid for legibility.
- Elevation comes from surface steps plus hairlines, not drop shadows.

### 5.5 The Orb (Pepper's presence)
Concentric rings: a solid core, a thin ring and a dashed outer ring. It is the only
element that glows.

| State | Visual | Haptic |
|---|---|---|
| Idle | Slow 6 s breathe, arc colour at 60% | none |
| Listening | Outer ring follows voice level | light tick on start |
| Thinking / working | Dashed ring rotates, speed ∝ activity | none |
| Speaking | Core pulses with speech amplitude | none |
| Needs you | Core turns amber, one slow pulse every 4 s | `.warning` once |
| Error / offline | Rings go grey, gap in outer ring | `.error` once |

With Reduce Motion on, each state becomes a static ring change with a crossfade.

### 5.6 Motion
- Springs only (`.snappy` for taps, `.smooth` for navigation). Durations of 0.25–0.4 s.
- Streaming text fades in per sentence, never typewriter-per-character.
- Tool rows slide in from the left edge, 40 ms apart.
- Matched geometry: the Home Orb grows into the Talk Orb.

### 5.7 Haptics and sound
- Approve → `.success`. Decline → `.rigid`. New blocking decision → `.warning`. Talk start → `.soft` impact.
- Optional sonic cues: a short two-note chime when Pepper starts speaking in voice mode. Off by default.

### 5.8 Accessibility
- VoiceOver labels on every icon button. The Orb announces its state ("Pepper is working: checking backups").
- Contrast ≥4.5:1 for text (tokens above are checked against `bg.void` and `bg.surface1`).
- Touch targets ≥44 pt. Full keyboard and Switch Control paths. Captions for every spoken brief.

---

## 6. iOS platform integration

| Feature | Framework | What it does |
|---|---|---|
| "Hey Siri, ask Pepper…" | App Intents + App Shortcuts | `AskPepperIntent`, `ApproveDecisionIntent`, `RunRoutineIntent`, `SystemStatusIntent` |
| Action Button / Control Center | App Intents + ControlWidget | One press opens Talk |
| Widgets | WidgetKit | Small: pending decisions · Medium: vitals + next routine · Lock Screen: Orb + count · StandBy |
| Live Activities | ActivityKit (push-updated) | Running sessions and scheduled runs, updated by the backend over APNs |
| Notifications | UserNotifications | Categories `DECISION`, `DECISION_RISKY`, `REPORT_READY`, `INCIDENT` with actions. Blocking = time-sensitive |
| Share extension | Share Extension | Send URL/PDF/image/text to Pepper with a quick instruction |
| Face ID | LocalAuthentication | Gate risky approvals and the Integrations screen |
| On-device speech | Speech (SpeechAnalyzer) | Private, fast transcription |
| Voice output | AVSpeechSynthesizer (baseline) · backend streaming TTS (premium; Sarvam for Indic voices) | Pepper's voice |
| Spotlight | CoreSpotlight | Index threads, decisions and files |
| Focus filters | App Intents `SetFocusFilterIntent` | Only blocking items during chosen Focus modes |
| Watch | watchOS app + complication | Talk, approve, Orb state |

---

## 7. App architecture

- **Target:** iOS 26+ (Liquid Glass, SpeechAnalyzer). Swift 6, SwiftUI, Observation, strict concurrency.
- **Modules (Swift packages):**
  - `PepperCore`: models, API client, SSE client, auth
  - `PepperStore`: SwiftData cache (threads, events, decisions, systems snapshot), offline-first reads
  - `PepperVoice`: capture, VAD, transcription, TTS, barge-in
  - `PepperUI`: design tokens, Orb, cards, chips, typography
  - Feature modules: `Brief`, `Talk`, `Threads`, `Decisions`, `Systems`, `Settings`
  - Extensions: `Widgets`, `LiveActivity`, `NotificationService` (rich pushes), `ShareExtension`, `Intents`
- **State:** one `@Observable` store per feature, fed by the API client and the cache.
- **Networking:** `URLSession.bytes` SSE with `Last-Event-ID` resume, reconnecting with backoff, and dedupe by event ID.
- **Auth:** passkey sign-in, then a per-device refresh token in the Keychain. Short-lived access JWT. No shared static token.
- **Background:** push-driven. Silent push → refresh the cache → update widgets. `BGAppRefreshTask` runs as a fallback.
- **Testing:** snapshot tests for every screen (dark/light, Dynamic Type XL), UI tests for approve and voice flows, and a mock backend.

---

## 8. Backend: what changes on top of this repo

### 8.1 Fixes to what exists
1. **Credentials to the vault:** `POST /api/credentials` writes to the Anthropic vault (`environment_variable` or MCP OAuth credentials), not a local file. SSH keys become vault env credentials; they are never typed on a phone.
2. **Escalations become a structured tool:** replace the `[ESCALATE]` regex with a custom tool `escalate` (strict JSON schema). The session waits for the answer, which comes back as a tool result, so scheduled runs can be answered.
3. **Scheduler to scheduled deployments:** Mon/Wed/Fri become Managed Agents deployments with `timezone: Asia/Kolkata` and outcome rubrics. APScheduler is removed.
4. **Async and non-blocking:** use `AsyncAnthropic` everywhere. No sync calls on the event loop.
5. **Persistence:** Postgres (or SQLite to start) for users, devices, threads, events, decisions, artifacts and audit.
6. **Streams:** open the stream before sending, and support resume via `Last-Event-ID` (backend replays stored events).
7. **Webhooks:** Anthropic webhooks (`session.status_idled`, etc.) trigger push notifications and Live Activity updates. External webhooks (UptimeRobot, GitHub) start incident sessions.

### 8.2 New API (v1)

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/auth/passkey/*` | Register / sign in; issues device tokens |
| GET | `/v1/brief` | Today's brief (cached, regenerated at 9:00 IST or on demand) |
| GET/POST | `/v1/threads` | List / start thread |
| POST | `/v1/threads/{id}/messages` | Send message (text or transcript + attachments) |
| GET | `/v1/threads/{id}/events` | SSE stream, resumable |
| GET | `/v1/decisions` · POST `/v1/decisions/{id}` | List / resolve (approve, edit, decline) |
| GET | `/v1/tasks` | Running sessions + progress (feeds Live Activities) |
| GET | `/v1/files/{id}` | Session outputs |
| GET | `/v1/systems` | Products, infra, renewals, spend snapshot |
| GET/POST/PATCH | `/v1/routines` | Scheduled deployments CRUD, run now, pause |
| GET/PUT | `/v1/memory/*` | Memory store documents + versions |
| GET/POST/DELETE | `/v1/integrations` | Vault-backed connections, OAuth start/callback |
| GET/PUT | `/v1/autonomy` | Per-area permission policy |
| GET | `/v1/usage` | Cost by day/task; budgets |
| POST | `/v1/devices` | APNs + Live Activity push tokens |
| POST | `/hooks/anthropic` · `/hooks/uptime` · `/hooks/github` | Inbound webhooks |

**SSE event schema to the app** (simplified from Managed Agents events):
`text.delta` · `activity.start` / `activity.end` (tool, target, status, ms) ·
`decision.created` · `file.created` · `status` (working / idle / needs_you / error) ·
`usage` · `done`. Every event has a monotonically increasing `id`.

### 8.3 Agent configuration (version-controlled YAML, applied with `ant`)
- `model: claude-opus-5`, with a session budget per interactive and scheduled run.
- Tools: agent toolset (bash, files, web). MCP servers: GitHub, Gmail, Google Calendar and others as needed. Custom tools: `escalate`, `notify`, `update_task_progress` (drives Live Activities).
- Permission policies mapped from the Autonomy screen (Observe → deny writes; Act & tell → `always_allow` + notify; Ask first → `always_ask`).
- Memory store `pepper-core` mounted read-write: `/profile.md`, `/voice.md` (writing style), `/products/*.md`, `/plan/8-week.md`, `/decisions/YYYY-MM.md`.
- Multiagent roster for heavy routines: coordinator + content writer + infra checker.

---

## 9. Roadmap

| Phase | Scope | Done when |
|---|---|---|
| **0: Foundations** | Backend fixes §8.1, v1 API, passkeys, Postgres, agent YAML, memory store | Scheduled Wed content can be approved from a notification and the agent continues |
| **1: MVP app** | Brief, Threads (streaming + activity), Decisions, Systems (read-only), push + actions, design system + Orb | You run a full week using only the app |
| **2: Voice & presence** | Talk mode, Siri/App Intents, Action Button, widgets, Live Activities | "Hold Action Button → ask → hear answer" in under 2 s to first word |
| **3: Reach** | Gmail/Calendar/GitHub MCP, share extension, incident auto-sessions, renewals, spend | An uptime alert produces a diagnosis before you open the app |
| **4: Trust & polish** | Autonomy dial, memory editor, audit log, budgets, Watch app, Focus filters, Indic voices | Every Pepper action is traceable and every area has an autonomy setting |

---

## 10. Open questions

1. Where is the existing iOS app source and `deploy_agent.py`? This plan assumes a fresh SwiftUI project if there's no salvageable code.
2. Single user (you) only, or will teammates (e.g. an Aakhyan co-founder) need their own logins and decision routing?
3. Voice languages: English only, or Hindi/Bengali too (Sarvam TTS/STT)?
4. Monthly ceiling for Anthropic spend, to size session and deployment budgets?
5. Which email and calendar are primary (Google Workspace?), and which social scheduler (Buffer?)?
