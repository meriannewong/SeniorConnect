from flask import Flask, request, jsonify
import numpy as np
import joblib
import tensorflow as tf

app = Flask(__name__)

print("loading model and scaler")
model = tf.keras.models.load_model("fall_mlp.keras")
scaler = joblib.load("mlp_scaler.pkl")
print("ready")

FINAL_THRESHOLD = 0.35  # same threshold used everywhere else in this project


@app.route("/", methods=["GET"])
def health():
    # simple endpoint to check the service is up, also useful for
    # measuring a "bare" round trip with no model computation involved
    return jsonify({"status": "ok"})


@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    # expects: {"features": [15 raw numbers, same order as processed_features.csv]}
    features = np.array(data["features"], dtype=np.float32).reshape(1, -1)
    scaled = scaler.transform(features)
    prob = float(model.predict(scaled, verbose=0)[0][0])
    fall_detected = bool(prob > FINAL_THRESHOLD)
    return jsonify({"probability": prob, "fall_detected": fall_detected})


if __name__ == "__main__":
    # local test only - Azure will use gunicorn to run this instead
    app.run(host="0.0.0.0", port=8000)
