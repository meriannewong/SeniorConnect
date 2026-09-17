import requests

# swap MODEL_URL depending on what's being tested against:
#   "https://fallmlp-mewong3.azurewebsites.net/predict" for the deployed cloud model
#   "http://localhost:8000/predict" if running app.py from cloud_baseline/ locally instead
MODEL_URL = "https://fallmlp-mewong3.azurewebsites.net/predict"

# update this once the dashboard itself is deployed to Azure App Service -
# for now it's just the local dashboard running on this machine
DASHBOARD_URL = "http://127.0.0.1:5000/api/alert"

# same real feature row used in test_azure_raw.py, so this is directly
# comparable to the numbers already in the build log
features = [-0.057925, 0.0037788060283639, -0.047, -0.067, -1.00646,
            0.0046923767964646, -0.993, -1.02, -0.0101399999999999,
            0.0048322251603169, 0.003, -0.022, 1.0081950083938311,
            0.004725468205627, 1.0219065515006742]


def decide_severity(fall_detected, probability):
    # fall_detected already comes from the model using the calibrated
    # threshold=0.35 chosen during MLP training (see threshold_analysis.py) -
    # so anything with fall_detected=True is already a real detection and
    # should always produce SOME alert, never get silently dropped.
    # severity here is just about HOW urgent that alert looks on the
    # dashboard, not about whether to alert at all.
    if not fall_detected:
        return None
    if probability >= 0.85:
        return "high"
    if probability >= 0.60:
        return "medium"
    return "low"  # still fall_detected=True, just closer to the 0.35 cutoff


if __name__ == "__main__":
    print("asking the model for a prediction...")
    prediction = requests.post(MODEL_URL, json={"features": features}, timeout=60).json()
    print("model said:", prediction)

    fall_detected = prediction["fall_detected"]
    probability = prediction["probability"]

    severity = decide_severity(fall_detected, probability)

    if severity is None:
        print("no fall detected, nothing sent to the dashboard")
    else:
        message = "Fall detected"
        print(f"severity = {severity}, sending alert to dashboard...")
        alert_response = requests.post(
            DASHBOARD_URL,
            json={"severity": severity, "message": message, "confidence": probability}
        )
        print("dashboard said:", alert_response.json())
        