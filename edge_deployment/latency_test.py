import time
import numpy as np
from hailo_platform import (HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams, InputVStreamParams, OutputVStreamParams, FormatType)

HEF_PATH = "./fall_mlp.hef"
TEST_DATA_PATH = "./test_data.npz"
N_RUNS = 200      # how many timed inferences to run
N_WARMUP = 10     # a few throwaway runs first, the very first call is often slower

print("loading a real row of test data to feed the model")
test_data = np.load(TEST_DATA_PATH, allow_pickle=True)
X_test = test_data["X_test"].astype(np.float32)
single_window = np.ascontiguousarray(X_test[0:1])  # one window at a time - this is how it runs in real use,
                                                   # one fall/no-fall decision every time a new sensor window comes in

print("loading HEF and configuring device")
hef = HEF(HEF_PATH)
devices = VDevice()

configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
network_group = devices.configure(hef, configure_params)[0]
network_group_params = network_group.create_params()

input_vstream_info = hef.get_input_vstream_infos()[0]
output_vstream_info = hef.get_output_vstream_infos()[0]

input_vstreams_params = InputVStreamParams.make(network_group, quantized=False, format_type=FormatType.FLOAT32)
output_vstreams_params = OutputVStreamParams.make(network_group, quantized=False, format_type=FormatType.FLOAT32)

with network_group.activate(network_group_params):
    with InferVStreams(network_group, input_vstreams_params, output_vstreams_params) as infer_pipeline:

        print("warming up (", N_WARMUP, "runs, not timed)")
        for _ in range(N_WARMUP):
            infer_pipeline.infer({input_vstream_info.name: single_window})

        print("timing", N_RUNS, "single-window inferences")
        times_ms = []
        for _ in range(N_RUNS):
            start = time.perf_counter()
            infer_pipeline.infer({input_vstream_info.name: single_window})
            end = time.perf_counter()
            times_ms.append((end - start) * 1000)

times_ms = np.array(times_ms)

print()
print("single-window inference latency (ms), n =", N_RUNS)
print("mean:  ", round(times_ms.mean(), 3))
print("median:", round(np.median(times_ms), 3))
print("min:   ", round(times_ms.min(), 3))
print("max:   ", round(times_ms.max(), 3))
print("std:   ", round(times_ms.std(), 3))
print("p90:   ", round(np.percentile(times_ms, 90), 3))
print("p96:   ", round(np.percentile(times_ms, 96), 3))
print("p99:   ", round(np.percentile(times_ms, 99), 3))
print("p95:   ", round(np.percentile(times_ms, 95), 3))
print("p99:   ", round(np.percentile(times_ms, 99), 3))

print()
print("throughput:", round(1000 / times_ms.mean(), 1), "windows/second (single-window loop)")
print()
print("note: this times the full python round trip (function call in, result out),")
print("not just the NPU's internal compute time - this is the honest number for")
print("'how fast does the deployed system respond', which is what the report needs")
