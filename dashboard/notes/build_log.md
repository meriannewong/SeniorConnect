# Build log

Keeping short notes here as I go - what I did, what broke, how I fixed it.
This doubles as material for the Implementation chapter and for
remembering my own reasoning before the demo.

## Template for each entry
- Date:
- What I worked on:
- What went wrong (if anything):
- How I fixed it / what I decided:

---

## Entries

- Date: 2026-07-27
- What I worked on: renamed project from SAMPARK to SeniorConnect for the
  dashboard piece, built the Objective 4 skeleton - Flask app with a live
  alerts page, a history page, and the /api/alert endpoint the Pi (via
  Azure) will send fall alerts to. Using SQLite locally for now so the
  whole flow (POST alert -> shows up on dashboard -> mark as seen ->
  still shows in history) can be tested before Azure Table Storage /
  Cosmos DB is wired in.
- What went wrong: nothing yet - tested the full flow with a fake POST
  request (like the Pi would send) and it worked: alert shows up with the
  right severity colour, "mark as seen" removes it from the main page but
  keeps it in history.
- How I fixed it / what I decided: kept storage swappable - only
  get_db()/setup_db() in app.py need to change when moving from SQLite to
  the real Azure storage, so this isn't wasted work.
- Still open: which Azure storage service to use (Table Storage vs Cosmos
  DB), how severity gets decided (raw string from Pi vs derived from
  model confidence), notification settings page not started, UREC2
  ethics approval status still needs confirming before Objective 5 can
  start.

- Date: 2026-07-27 (later same day)
- What I worked on: got the dashboard running locally (venv_tf, PowerShell)
  - main gotchas were PowerShell 5.1 not supporting `&&` (used `;` instead)
  and downloaded files landing in Downloads instead of the project folder.
  Confirmed full flow works: POST alert -> shows on dashboard -> mark as
  seen -> still in history. Then added real Azure Table Storage support to
  app.py, decided Table Storage over Cosmos DB (simpler, cheaper, fits a
  small key-value alert log, same resource group pattern as the
  fallmlp-mewong3 cloud benchmark app). Kept the SQLite path as an
  automatic fallback (picked by checking for AZURE_STORAGE_CONNECTION_STRING
  env var) so I'm not stuck without a working demo if Azure/wifi is
  unreliable on the day.
- What went wrong: nothing major - tested the Azure code path with a fake
  in-memory table client (no real Azure account needed yet) to catch bugs
  before actually creating the storage account. Both modes pass the same
  test flow.
- How I fixed it / decided: severity should be computed at the inference
  step (Pi edge model or cloud /predict baseline), not on the dashboard -
  keeps the dashboard's job as purely "display and log", which is a
  cleaner story for the report/viva than mixing decision logic into
  Objective 4. Suggested thresholds: >=0.90 probability = high, 0.70-0.90
  = medium, below that = don't alert. Not yet validated against labelled
  data - flagged as a limitation to mention in the report.
- Still open: haven't actually created the Azure Storage Account resource
  yet (next physical step), Pi/cloud inference script doesn't yet send
  severity in the POST body, notification settings page, auth/access
  control on the dashboard, deploying this app itself to Azure App Service
  so the Pi can reach it from outside localhost.

- Date: 2026-07-27 (later still)
- What I worked on: created Azure Storage Account (seniorconnectdb01,
  Standard, LRS, same resource group as fallmlp-mewong3), swapped in the
  connection string, confirmed the `alerts` table gets created in real
  Azure and a test alert actually lands in it - dashboard is genuinely
  cloud-connected now, not just local SQLite. Also had to rotate the
  storage account key after accidentally pasting the full connection
  string somewhere it shouldn't have gone - good reminder to treat that
  string like a password from now on.
  Then wrote send_alert_demo.py in cloud_baseline/, which is the actual
  missing link: calls the model's /predict endpoint, decides severity
  from the response, and POSTs to the dashboard - this is the first
  script that runs the WHOLE chain end to end rather than testing the
  model or the dashboard in isolation.
- What went wrong / important correction: my first severity plan (>=0.90
  high, 0.70-0.90 medium, below 0.70 don't alert) was WRONG for this
  project - it would have silently dropped real detections, since the
  MLP's calibrated threshold from training is 0.35, not 0.70. A real
  example from earlier testing had probability=0.48 and fall_detected=true
  - under the old plan that would never have alerted at all, defeating
  the whole point of tuning the threshold for high recall.
- How I fixed it / decided: fall_detected is the actual alert trigger
  (already using the calibrated 0.35 threshold) - severity only decides
  HOW URGENT the alert looks, it never decides whether to alert at all.
  New thresholds: >=0.85 probability = high, 0.60-0.85 = medium, anything
  else where fall_detected is still true = low. Tested this logic against
  several cases including the real 0.48 example, all correct. Also tested
  the full script end to end with mocked responses (no real network calls
  needed) before trusting it.
- Still open: send_alert_demo.py currently sends one fixed test feature
  row, same as test_azure_raw.py - still need to decide how this connects
  to whatever will be running continuously on the Pi in the real
  deployment (this script is a proof-of-concept for the logic, not the
  final always-on Pi script). Notification settings page, auth on
  dashboard, deploying dashboard itself to Azure App Service still open.
  UREC2 status still needs confirming.

- Date: 2026-07-27 (later still)
- What I worked on: confirmed send_alert_demo.py works end to end against
  the real local dashboard (was just missing app.py running in a second
  terminal - not a bug, just needed both processes up at once). Then
  decided the raw confidence number ("Fall detected (model confidence
  0.48)") shouldn't be in the message shown to caregivers - it's not
  meaningful to a non-technical person and the severity colour already
  communicates urgency. Kept the confidence value but moved it: message
  is now just "Fall detected", confidence is sent as its own field, stored
  in the database, and shown only as a percentage in the /history table -
  useful for my own evaluation/report writing without cluttering the
  caregiver-facing card.
- How I fixed it: added a confidence column to the SQLite schema and to
  the Azure entity dict, updated /api/alert to accept it as an optional
  field, updated history.html to show it (or "-" if not provided, so
  manual test alerts without a confidence value still display fine).
  Tested both storage modes (SQLite and the fake in-memory Azure client)
  with and without confidence in the POST body before shipping.
- Still open: same as before - deciding what actually runs continuously
  on the Pi, notification settings page, auth on dashboard, deploying
  dashboard to Azure App Service, UREC2 status.

- Date: 2026-07-27 (later still)
- What I worked on: deployed the dashboard itself to Azure App Service
  (seniorconnect-mewong3, same resource group/region/sku as the
  fallmlp-mewong3 model API - fallmlp-rg-uk, ukwest, F1). Set
  AZURE_STORAGE_CONNECTION_STRING as an App Service application setting
  (not just a local env var, since the cloud server needed its own copy).
  Hit the same http->https redirect 405 issue as before with /predict -
  same fix, same root cause (App Service forces https, POST gets
  downgraded to GET on redirect). Updated send_alert_demo.py's
  DASHBOARD_URL to the real https:// cloud address. Confirmed the full
  chain end to end: cloud model (/predict) -> severity decision ->
  cloud dashboard (/api/alert) -> Azure Table Storage -> visible on
  both the live dashboard and /history. No longer need two terminals
  open locally - both pieces run on Azure now.
- Milestone: this is Objective 4's core requirement ("integrating Azure
  cloud services for real-time notification and event logging") actually
  met end to end, not just simulated locally.
- Still open: notification settings page (toggle on/off, maybe
  email/SMS), auth/access control on the dashboard (still flagged as a
  known limitation, not fixed), deciding what continuously runs on the
  Pi in the real deployment (send_alert_demo.py is proof-of-concept with
  one fixed test row, not the final always-on script), UREC2 ethics
  approval status still needs confirming before Objective 5 can start.

- Date: 2026-07-27 (later still)
- What I worked on: added a new /profile page - a "resident profile"
  concept view with personal details, allergies/conditions, medication
  history + reminders, vitals (temperature/heart rate/blood
  pressure/oxygen), a 7-day activity chart, and lab results (blood
  sugar, haemoglobin, white blood cells, lymphocytes).
- Important decision: this page is 100% hardcoded demo data, not wired
  to any database or sensor. Reasoning: adding real personal health
  records (name, DOB, blood group, medical history) would meaningfully
  expand the system's scope beyond what Objective 4 actually covers
  (a fall-alert dashboard) and beyond what UREC2 was likely scoped for.
  Framed instead as a concept preview for Objective 6 ("future directions
  for extending SeniorConnect toward broader elderly-care companionship
  functions") - there's a visible banner on the page itself saying this
  clearly, so it can't be mistaken for a working part of the evaluated
  system. Worth repeating this framing in the report if this page gets
  shown in screenshots or the demo.
  Matches the visual language already established elsewhere in the app
  (sage/pine palette, Fraunces + Inter fonts, pill-shaped nav) rather
  than introducing a different style just for this page.
- Still open: notification settings page, auth on dashboard, deciding
  what runs continuously on the Pi, UREC2 status.

- Date: 2026-07-27 (later still)
- What I worked on: refined the /profile concept page after looking at
  two reference dashboards. Borrowed the STRUCTURE of a few patterns
  (an "at a glance" stat strip - adherence/streak/avg BP/avg glucose,
  a checkable "today's medication" tracker with a progress bar instead
  of a plain list, and a callout connecting vitals back to the real
  alert system) but deliberately kept the existing sage/pine/Fraunces
  visual language rather than copying the reference designs' bright
  purple/teal gradient look - didn't want this one page to look like a
  different product bolted onto the rest of the app, and didn't want to
  closely clone someone else's specific visual design, just borrow the
  general layout idea (stat strips and dose trackers are common patterns
  across health apps generally, not unique to those two references).
- Nice side effect: the "bridge callout" on the vitals section explicitly
  says any future vitals-based alert would go through the SAME alert
  system already built and evaluated for fall detection - this is a
  genuinely useful line for the report, since it shows the future-work
  vision (Objective 6) is a natural extension of working infrastructure,
  not a separate wishlist.
- Still open: notification settings page, auth on dashboard, deciding
  what runs continuously on the Pi, UREC2 status.

- Date: 2026-07-27 (later still)
- What I worked on: rebuilt /profile as a fixed one-screen CSS Grid
  dashboard instead of a stacked, scrolling page - everything (resident
  card, heart rate, blood pressure, temperature/oxygen, lab analysis,
  medication, recent activity) is visible at once on a normal laptop
  screen, no scrolling the page itself. Dropped the separate medication
  history table and the standalone "at a glance" stat row from the
  compact view to fit everything - adherence/streak now show as small
  stats inside the resident card instead, and medication history is
  implied by the "active prescriptions" in the dose tracker rather than
  a full separate table (that fuller table still exists in the earlier
  version of this page if it's ever needed again).
- How: body.profile-shell is height:100vh + overflow:hidden, the grid
  uses grid-template-areas (250px left column for the resident card,
  two flexible columns on the right, 4 rows). Individual cards that
  could have more content than fits (lab list, medication doses) scroll
  WITHIN their own card via .panel-scroll rather than the whole page
  scrolling - this is the standard way real dashboards handle "no page
  scroll" without silently hiding data.
- Important limitation: this dense grid only makes sense on a normal
  laptop/desktop screen. Added a media query below 1000px width that
  falls back to a normal stacked, scrollable layout - trying to force
  this much content into one screen on a phone would make everything
  unreadably small, so narrow screens intentionally get the older,
  more spacious behaviour instead.
- Still open: notification settings page, auth on dashboard, deciding
  what runs continuously on the Pi, UREC2 status.
  