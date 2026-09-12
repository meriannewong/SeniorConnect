import os
import re
import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)  # one level up from preprocessing/

# ---------------- SETTINGS ----------------

KFALL_SENSOR_FOLDER = os.path.join(PROJECT_ROOT, "data", "KFall", "sensor_data_new")
KFALL_LABEL_FOLDER = os.path.join(PROJECT_ROOT, "data", "KFall", "label_data_new")

# FallAllD is nested one level deeper: data/FallAllD/FallAllD/ has the
# actual .dat files, the outer FallAllD folder is just the extracted zip
FALLALLD_FOLDER = os.path.join(PROJECT_ROOT, "data", "FallAllD", "FallAllD")

URFD_FOLDER = os.path.join(PROJECT_ROOT, "data", "URFD")

OUTPUT_FILE = os.path.join(PROJECT_ROOT, "results", "processed_features.csv")

WINDOW_SECONDS = 2      # each window is 2 seconds of data
OVERLAP = 0.5           # windows overlap by 50%, gives more training samples

SAMPLE_RATE_KFALL = 100     # confirmed 100Hz, matches the 0.01s steps in TimeStamp(s)
SAMPLE_RATE_FALLALLD = 238  # confirmed 238Hz, matches 4760 samples over 20s

# LSM9DS1 accelerometer used in FallAllD, +-8g range -> 0.244 mg per raw count
FALLALLD_ACC_SENSITIVITY = 0.000244

# CHECK: which device number is the waist? using device 1 for now so it's
# at least consistent, update this once confirmed
FALLALLD_DEVICE_TO_USE = "1"

# FallAllD has no onset label, only a known impact point (centred at the
# 10th second of each instance). This is an assumption, not a documented
# fact from the dataset - treat the last N seconds before impact as the
# pre-impact segment. Document this choice in the Methodology.
FALLALLD_PRE_IMPACT_SECONDS = 2


# ---------------- SHARED HELPER FUNCTIONS ----------------

def make_windows(acc, window_size, step_size):
    windows = []
    start = 0
    while start + window_size <= len(acc):
        windows.append(acc[start:start + window_size])
        start += step_size
    return windows


def make_windows_with_start(acc, window_size, step_size):
    # same as make_windows but also hands back where each window starts,
    # needed so KFall can check a window's position against onset/impact
    windows = []
    starts = []
    start = 0
    while start + window_size <= len(acc):
        windows.append(acc[start:start + window_size])
        starts.append(start)
        start += step_size
    return windows, starts


def make_windows_by_time(acc, time_ms, window_ms, step_ms):
    windows = []
    if len(time_ms) == 0:
        return windows

    start_time = time_ms[0]
    end_time = time_ms[-1]
    current_start = start_time

    while current_start + window_ms <= end_time:
        mask = (time_ms >= current_start) & (time_ms < current_start + window_ms)
        if mask.sum() > 0:
            windows.append(acc[mask])
        current_start += step_ms

    return windows


def get_features(window):
    feats = {}
    axis_names = ["x", "y", "z"]

    for i in range(3):
        col = window[:, i]
        feats["acc_" + axis_names[i] + "_mean"] = np.mean(col)
        feats["acc_" + axis_names[i] + "_std"] = np.std(col)
        feats["acc_" + axis_names[i] + "_max"] = np.max(col)
        feats["acc_" + axis_names[i] + "_min"] = np.min(col)

    magnitude = np.sqrt(window[:, 0] ** 2 + window[:, 1] ** 2 + window[:, 2] ** 2)
    feats["mag_mean"] = np.mean(magnitude)
    feats["mag_std"] = np.std(magnitude)
    feats["mag_max"] = np.max(magnitude)

    return feats


# ---------------- KFALL ----------------

def find_kfall_label_file(subject_id):
    for root, dirs, files in os.walk(KFALL_LABEL_FOLDER):
        for f in files:
            if subject_id in f and f.endswith(".xlsx"):
                return os.path.join(root, f)
    return None


def extract_task_id(text):
    match = re.search(r"\((\d+)\)", str(text))
    if match:
        return int(match.group(1))
    return None


def load_kfall():
    rows = []

    if not os.path.isdir(KFALL_SENSOR_FOLDER):
        print("KFall sensor folder not found:", KFALL_SENSOR_FOLDER)
        return rows

    subjects = [s for s in os.listdir(KFALL_SENSOR_FOLDER)
                if os.path.isdir(os.path.join(KFALL_SENSOR_FOLDER, s))]

    name_pattern = re.compile(r"^[A-Za-z]+\d+T(\d+)R(\d+)\.csv$", re.IGNORECASE)

    window_size = int(WINDOW_SECONDS * SAMPLE_RATE_KFALL)
    step_size = int(window_size * (1 - OVERLAP))

    dropped_after_impact = 0
    missing_onset_impact = 0

    for subject in subjects:
        subject_path = os.path.join(KFALL_SENSOR_FOLDER, subject)

        label_path = find_kfall_label_file(subject)
        if label_path is None:
            print("no label file for", subject, "- skipping this subject")
            continue

        labels_df = pd.read_excel(label_path)
        labels_df["Task Code (Task ID)"] = labels_df["Task Code (Task ID)"].ffill()
        labels_df["task_id_num"] = labels_df["Task Code (Task ID)"].apply(extract_task_id)

        for f in os.listdir(subject_path):
            match_name = name_pattern.match(f)
            if not match_name:
                continue

            task_num, trial_num = match_name.groups()

            data = pd.read_csv(os.path.join(subject_path, f))
            acc = data[["AccX", "AccY", "AccZ"]].values

            match_row = labels_df[
                (labels_df["task_id_num"] == int(task_num)) &
                (labels_df["Trial ID"] == int(trial_num))
            ]
            is_fall_trial = len(match_row) > 0

            # pull the onset/impact frame for this trial if it's a fall.
            # this is what was missing before - every window in a fall
            # trial used to get label=1 no matter where it sat in the trial
            onset_frame = None
            impact_frame = None
            if is_fall_trial:
                onset_val = match_row["Fall_onset_frame"].values[0]
                impact_val = match_row["Fall_impact_frame"].values[0]
                if pd.isna(onset_val) or pd.isna(impact_val):
                    missing_onset_impact += 1
                else:
                    onset_frame = int(onset_val)
                    impact_frame = int(impact_val)

            windows, starts = make_windows_with_start(acc, window_size, step_size)

            for w, window_start in zip(windows, starts):
                window_end = window_start + window_size

                if not is_fall_trial:
                    label = 0
                elif onset_frame is None:
                    # couldn't read onset/impact for this trial, fall back
                    # to the old behaviour rather than lose the trial
                    label = 1
                elif window_end <= onset_frame:
                    label = 0  # still before the fall starts
                elif window_end <= impact_frame:
                    label = 1  # this is the pre-impact segment
                else:
                    dropped_after_impact += 1
                    continue  # window reaches into or past impact, skip it

                feats = get_features(w)
                feats["label"] = label
                feats["source"] = "kfall"
                feats["subject_id"] = "kfall_" + subject
                feats["activity_detail"] = "T" + task_num
                rows.append(feats)

    print("KFall done, windows made:", len(rows))
    print("KFall windows dropped (reached impact or later):", dropped_after_impact)
    print("KFall fall trials with missing onset/impact values:", missing_onset_impact)
    return rows


# ---------------- FALLALLD ----------------

def load_fallalld():
    rows = []

    if not os.path.isdir(FALLALLD_FOLDER):
        print("FallAllD folder not found:", FALLALLD_FOLDER)
        return rows

    name_pattern = re.compile(r"S(\d+)_D(\d+)_A(\d+)_T(\d+)_A\.dat$", re.IGNORECASE)

    files = [f for f in os.listdir(FALLALLD_FOLDER) if name_pattern.search(f)]

    if len(files) == 0:
        print("no matching .dat files found in", FALLALLD_FOLDER)

    window_size = int(WINDOW_SECONDS * SAMPLE_RATE_FALLALLD)
    step_size = int(window_size * (1 - OVERLAP))
    pre_impact_frames = int(FALLALLD_PRE_IMPACT_SECONDS * SAMPLE_RATE_FALLALLD)

    dropped_after_impact = 0

    for f in files:
        match = name_pattern.search(f)
        subject_num, device_num, activity_num, trial_num = match.groups()

        if device_num != FALLALLD_DEVICE_TO_USE:
            continue

        activity_id = int(activity_num)
        is_fall = activity_id >= 100

        data = pd.read_csv(os.path.join(FALLALLD_FOLDER, f), header=None,
                            names=["accX", "accY", "accZ"])
        acc = data[["accX", "accY", "accZ"]].values * FALLALLD_ACC_SENSITIVITY

        # impact is documented as centred at the 10th second of each
        # instance - use the actual file length rather than a hardcoded
        # frame number in case a file isn't exactly 20s of data
        impact_frame = len(acc) // 2
        pre_impact_start = max(0, impact_frame - pre_impact_frames)

        windows, starts = make_windows_with_start(acc, window_size, step_size)

        for w, window_start in zip(windows, starts):
            window_end = window_start + window_size

            if not is_fall:
                label = 0
            elif window_end <= pre_impact_start:
                label = 0  # well before the assumed pre-impact segment
            elif window_end <= impact_frame:
                label = 1  # within the assumed pre-impact segment
            else:
                dropped_after_impact += 1
                continue  # reaches into or past the impact point, skip it

            feats = get_features(w)
            feats["label"] = label
            feats["source"] = "fallalld"
            feats["subject_id"] = "fallalld_S" + subject_num
            feats["activity_detail"] = "A" + activity_num
            rows.append(feats)

    print("FallAllD done, windows made:", len(rows))
    print("FallAllD windows dropped (reached impact or later):", dropped_after_impact)
    return rows


# ---------------- URFD ----------------

def load_urfd():
    rows = []

    if not os.path.isdir(URFD_FOLDER):
        print("URFD folder not found:", URFD_FOLDER)
        return rows

    files = [f for f in os.listdir(URFD_FOLDER) if f.endswith(".csv") and "acc" in f.lower()]

    for f in files:
        data = pd.read_csv(
            os.path.join(URFD_FOLDER, f),
            header=None,
            names=["time_ms", "sv_total", "accX", "accZ", "accY"]
        )

        acc = data[["accX", "accY", "accZ"]].values
        time_ms = data["time_ms"].values

        is_fall = f.lower().startswith("fall")

        window_ms = WINDOW_SECONDS * 1000
        step_ms = int(window_ms * (1 - OVERLAP))
        windows = make_windows_by_time(acc, time_ms, window_ms, step_ms)

        for w in windows:
            feats = get_features(w)
            feats["label"] = 1 if is_fall else 0
            feats["source"] = "urfd"
            feats["activity_detail"] = "fall" if is_fall else "adl"
            feats["subject_id"] = "urfd_" + f
            rows.append(feats)

    print("URFD done, windows made:", len(rows))
    return rows


# ---------------- MAIN ----------------

if __name__ == "__main__":
    all_rows = []
    all_rows += load_kfall()
    all_rows += load_fallalld()
    all_rows += load_urfd()

    final_df = pd.DataFrame(all_rows)

    print()
    print("total windows:", len(final_df))
    print(final_df["label"].value_counts())
    print(final_df["source"].value_counts())
    print("unique subjects:", final_df["subject_id"].nunique())

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    final_df.to_csv(OUTPUT_FILE, index=False)
    print("saved to", OUTPUT_FILE)
    