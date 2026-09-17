# SeniorConnect dashboard (Objective 4)

Caregiver-facing alert dashboard. Receives fall alerts and shows them live, plus a history log.

## How to run it

Two modes, picked automatically depending on whether an Azure connection
string is set.

**Mode A - local only, no Azure yet (good for quick testing):**
```
cd dashboard
pip install -r requirements.txt
python app.py
```
A SQLite file `seniorconnect.db` will be created automatically. Terminal
prints `Storage mode: local SQLite ...` on startup, so the active mode
is always visible.

**Mode B - connected to real Azure Table Storage:**

1. Create a Storage Account (skip if already set up from the cloud
   benchmark work): Azure Portal -> Create a resource -> Storage account ->
   fill in resource group / name / region -> Review + create.
2. Once created, open the Storage Account -> "Access keys" (left sidebar) ->
   copy the "Connection string" under key1.
3. Set it as an environment variable in the PowerShell session (only lasts
   for that terminal window - needs re-running each time a new one opens,
   or use `setx` instead of `$env:` for it to persist permanently):
   ```
   $env:AZURE_STORAGE_CONNECTION_STRING = "paste the connection string here"
   ```
4. Then run the app the same way:
   ```
   python app.py
   ```
   Terminal should now print `Storage mode: Azure Table Storage`. A table
   called `alerts` will be created automatically inside the storage account
   the first time an alert comes in.

Never commit the real connection string to git / hand it in with the
report - it's a credential, treat it like a password. Worth a one-line
mention in the report's limitations or implementation notes that the
connection string is read from an environment variable rather than
hardcoded, as a basic security practice.

## How to test it sends/receives correctly (before the real Pi is wired up)

From another terminal, while app.py is running:

```
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/alert" -Method Post -ContentType "application/json" -Body '{"severity": "high", "message": "Fall detected, no movement after"}'
```

Refresh the dashboard page (or wait 5 seconds, it auto-refreshes) and the alert
should show up as a red card. Click "Mark as seen" to move it off the main
page, then check /history to confirm it's still logged there. This works
identically in both storage modes.

## What's built so far

- `/` - shows alerts not yet marked as seen, auto-refreshes every 5s
- `/history` - full log of every alert, seen or not
- `POST /api/alert` - endpoint the Pi (via Azure) will send fall alerts to
- `POST /api/alert/<id>/ack` - caregiver marks an alert as seen
- Storage layer swaps between local SQLite and Azure Table Storage based on
  whether `AZURE_STORAGE_CONNECTION_STRING` is set - routes/templates don't
  change either way

## How severity should be decided (recommendation)

Compute it where the model already runs (edge inference on the Pi, or the
cloud `/predict` baseline), not on the dashboard. The dashboard's job stays
"display and log what was decided" - keeps a clean separation between the
edge-AI component (Objectives 2/3) and the dashboard component (Objective 4),
which reads well in the report and in the viva.

Suggested thresholds based on the model's fall-class probability:
- `>= 0.90` -> `"high"`
- `0.70 - 0.90` -> `"medium"`
- below whatever threshold is already being used to call something a fall
  at all -> don't send an alert

Wherever the Pi/cloud script currently does something like
`prediction = model.predict(features)`, it would also have access to the
probability for the fall class. That's the value to threshold against
before building the POST body, e.g. (adjust variable names to match the
actual inference script):

```python
if fall_probability >= 0.90:
    severity = "high"
elif fall_probability >= 0.70:
    severity = "medium"
else:
    severity = None  # not confident enough to alert

if severity:
    requests.post("https://<app-url>/api/alert", json={
        "severity": severity,
        "message": "Fall detected, no movement after"
    })
```

These threshold numbers are a starting point, not something validated -
worth mentioning in the report that they were chosen for demonstration and
would ideally be tuned against labelled data (e.g. how often a 0.75
probability window was actually a real fall vs a false positive in the
test set).

## What's still needed to match the full Objective 4 scope

1. **Notification settings page** (toggle on/off, maybe email/SMS via Azure)
   - not built yet, was in the original placeholder plan.
2. **Auth / access control** - right now anyone who reaches the URL sees the
   dashboard. Worth flagging in the report as a limitation if not addressed,
   especially since this touches the ethics/data-handling side of the
   caregiver evaluation.
3. **Deploy this app to Azure App Service** (not just local Flask) so the Pi
   can actually reach it from outside the laptop - same `az webapp up`
   pattern already used for the cloud benchmark app.
   