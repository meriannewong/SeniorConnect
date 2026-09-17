import numpy as np
from hailo_sdk_client import ClientRunner, InferenceContext

# --- file paths (WSL2) ---
TFLITE_PATH = "./fall_mlp_float32.tflite"
CALIBRATION_PATH = "./calibration_data.npy"
TEST_DATA_PATH = "./test_data.npz"
# ------------------------------------------------------

MODEL_NAME = "fall_mlp"
HW_ARCH = "hailo8"
FINAL_THRESHOLD = 0.35  # same threshold picked on val earlier

print("loading data")
calib_dataset = np.load(CALIBRATION_PATH)
test_data = np.load("test_data.npz", allow_pickle = True)
X_test = test_data["X_test"]
y_test = test_data["y_test"]
source_test = test_data["source_test"]
print("test set size:", X_test.shape)

print("parsing", TFLITE_PATH)
runner = ClientRunner(hw_arch=HW_ARCH)
hn, npz = runner.translate_tf_model(TFLITE_PATH, MODEL_NAME)

print("running optimize (quantisation)")
runner.optimize(calib_dataset)


def evaluate(probs, label):
    preds = (probs.flatten() > FINAL_THRESHOLD).astype(int)
    acc = (preds == y_test).mean()
    tp = ((preds == 1) & (y_test == 1)).sum()
    fn = ((preds == 0) & (y_test == 1)).sum()
    recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    print(f"\n[{label}] accuracy={acc:.4f}, fall_recall={recall:.4f}")
    for src in np.unique(source_test):
        mask = source_test == src
        src_acc = (preds[mask] == y_test[mask]).mean()
        fall_mask = mask & (y_test == 1)
        src_recall = (preds[fall_mask] == 1).mean() if fall_mask.sum() > 0 else float("nan")
        print(f"  {src}: accuracy={src_acc:.4f}, fall_recall={src_recall:.4f}")


print("\nrunning float (SDK_NATIVE) inference for sanity check")
with runner.infer_context(InferenceContext.SDK_NATIVE) as ctx:
    native_probs = runner.infer(ctx, X_test)
evaluate(native_probs, "FLOAT (pre-quantisation)")

print("\nrunning quantized (SDK_QUANTIZED) inference - this is what the .hef will actually do")
with runner.infer_context(InferenceContext.SDK_QUANTIZED) as ctx:
    quantized_probs = runner.infer(ctx, X_test)
evaluate(quantized_probs, "QUANTIZED (matches .hef behavior)")

print("\ncompare the two accuracy/recall numbers above - a drop of a few percentage")
print("points is normal for INT8 quantisation; a large drop means we should")
print("increase the calibration dataset size and re-optimize before deploying")
