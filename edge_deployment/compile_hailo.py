import numpy as np
from hailo_sdk_client import ClientRunner

TFLITE_PATH = "./fall_mlp_float32.tflite"
CALIBRATION_PATH = "./calibration_data.npy"
OUTPUT_PATH = "./fall_mlp.hef"

MODEL_NAME = "fall_mlp"
HW_ARCH = "hailo8"

print("loading calibration data from", CALIBRATION_PATH)
calib_dataset = np.load(CALIBRATION_PATH)

print("parsing", TFLITE_PATH)
runner = ClientRunner(hw_arch=HW_ARCH)
runner.translate_tf_model(TFLITE_PATH, MODEL_NAME)
print("parsed successfully")

print("running optimize (quantization) - same as your evaluate_quantized.py run")
runner.optimize(calib_dataset)
print("optimize done")

print("compiling to HEF - this is the step evaluate_quantized.py never ran")
hef = runner.compile()

with open(OUTPUT_PATH, "wb") as f:
    f.write(hef)

print("saved HEF to", OUTPUT_PATH)
print("this is the file to copy to the Raspberry Pi")
