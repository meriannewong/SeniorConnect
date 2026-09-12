import numpy as np
from hailo_platform import (HEF, VDevice, HailoStreamInterface, InferVStreams,
                             ConfigureParams, InputVStreamParams, OutputVStreamParams,
                             FormatType)

HEF_PATH = "./fall_mlp.hef"
TEST_DATA_PATH = "./test_data.npz"
FINAL_THRESHOLD = 0.35  # same threshold as everywhere else in this project

print("loading test set")
test_data = np.load(TEST_DATA_PATH, allow_pickle=True)
X_test = test_data["X_test"]
y_test = test_data["y_test"]
source_test = test_data["source_test"]
print("test set shape:", X_test.shape)

print("loading HEF and configuring device")
hef = HEF(HEF_PATH)
devices = VDevice()

configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
network_group = devices.configure(hef, configure_params)[0]
network_group_params = network_group.create_params()

input_vstream_info = hef.get_input_vstream_infos()[0]
output_vstream_info = hef.get_output_vstream_infos()[0]
print("input node:", input_vstream_info.name, "output node:", output_vstream_info.name)

input_vstreams_params = InputVStreamParams.make(network_group, quantized=False, format_type=FormatType.FLOAT32)
output_vstreams_params = OutputVStreamParams.make(network_group, quantized=False, format_type=FormatType.FLOAT32)

# quick sanity check on 5 rows first, before committing to the full test set
print()
print("quick sanity check on first 5 rows:")
with network_group.activate(network_group_params):
    with InferVStreams(network_group, input_vstreams_params, output_vstreams_params) as infer_pipeline:
        small_input = {input_vstream_info.name: X_test[:5].astype(np.float32)}
        small_result = infer_pipeline.infer(small_input)
        print(small_result[output_vstream_info.name].flatten())
print("^ these should look like probabilities between 0 and 1, not garbage/NaN")

print()
print("running full test set (", len(X_test), "rows ) on real hardware")
with network_group.activate(network_group_params):
    with InferVStreams(network_group, input_vstreams_params, output_vstreams_params) as infer_pipeline:
        input_data = {input_vstream_info.name: X_test.astype(np.float32)}
        results = infer_pipeline.infer(input_data)

y_prob = np.array(results[output_vstream_info.name]).flatten()
y_pred = (y_prob > FINAL_THRESHOLD).astype(int)


def report(y_true, y_pred, label=""):
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    acc = (tp + tn) / len(y_true) if len(y_true) > 0 else float("nan")
    recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
    print(f"{label:>10} n={len(y_true):>6} accuracy={acc:.4f} fall_recall={recall:.4f} fall_precision={precision:.4f}")
    return acc, recall, precision


print()
print(f"REAL HARDWARE test set results at threshold = {FINAL_THRESHOLD}")
hw_acc, hw_recall, hw_prec = report(y_test, y_pred, "overall")

print()
print("per data source:")
for src in np.unique(source_test):
    mask = source_test == src
    report(y_test[mask], y_pred[mask], str(src))

# numbers from the WSL2 SDK_QUANTIZED emulator run, for a direct side-by-side
EMULATOR_BASELINE = {"accuracy": 0.8471, "recall": 0.8047}

print()
print("=== real hardware vs WSL2 emulator, overall ===")
print(f"accuracy:    emulator={EMULATOR_BASELINE['accuracy']:.4f}  hardware={hw_acc:.4f}  diff={hw_acc - EMULATOR_BASELINE['accuracy']:+.4f}")
print(f"fall_recall: emulator={EMULATOR_BASELINE['recall']:.4f}  hardware={hw_recall:.4f}  diff={hw_recall - EMULATOR_BASELINE['recall']:+.4f}")
print()
print("these two should be very close (same INT8 math) - if diff is basically 0,")
print("that confirms the emulator faithfully predicted real hardware behaviour")
