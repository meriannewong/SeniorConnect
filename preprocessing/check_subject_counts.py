import os
import re

KFALL_SENSOR_FOLDER = "data/KFall/sensor_data_new"
KFALL_LABEL_FOLDER = "data/KFall/label_data_new"
FALLALLD_FOLDER = "data/FallAllD/FallAllD"
URFD_FOLDER = "data/URFD"


print("---- KFall ----")
subjects = [s for s in os.listdir(KFALL_SENSOR_FOLDER)
            if os.path.isdir(os.path.join(KFALL_SENSOR_FOLDER, s))]
print("subject folders found:", len(subjects))

missing_label = []
for subject in subjects:
    found = False
    for root, dirs, files in os.walk(KFALL_LABEL_FOLDER):
        for f in files:
            if subject in f and f.endswith(".xlsx"):
                found = True
    if not found:
        missing_label.append(subject)

print("subjects WITH a label file:", len(subjects) - len(missing_label))
print("subjects MISSING a label file:", missing_label)


print()
print("---- FallAllD ----")
name_pattern = re.compile(r"S(\d+)_D(\d+)_A(\d+)_T(\d+)_A\.dat$", re.IGNORECASE)
subject_nums = set()
for f in os.listdir(FALLALLD_FOLDER):
    match = name_pattern.search(f)
    if match:
        subject_num, device_num, activity_num, trial_num = match.groups()
        if device_num == "1":  # same device filter as preprocess.py
            subject_nums.add(subject_num)

print("unique subjects found (device 1 only):", len(subject_nums))
print("subject numbers:", sorted(subject_nums))


print()
print("---- URFD ----")
files = [f for f in os.listdir(URFD_FOLDER) if f.endswith(".csv") and "acc" in f.lower()]
fall_files = [f for f in files if f.lower().startswith("fall")]
adl_files = [f for f in files if f.lower().startswith("adl")]
print("total acc files:", len(files))
print("fall files:", len(fall_files), "adl files:", len(adl_files))
print("expected: 30 fall + 40 adl = 70")
