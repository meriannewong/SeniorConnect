import os
import pandas as pd

# KFall comes as two separate folders - sensor_data_new has the actual
# motion csv files, label_data_new has the fall timing info
KFALL_SENSOR_FOLDER = "../data/KFall/sensor_data_new"
KFALL_LABEL_FOLDER = "../data/KFall/label_data_new"
FALLALLD_PICKLE = "../data/FallAllD/FallAllD.pkl"
URFD_FOLDER = "../data/URFD"

print("---- KFall sensor data ----")
subjects = [s for s in os.listdir(KFALL_SENSOR_FOLDER) if os.path.isdir(os.path.join(KFALL_SENSOR_FOLDER, s))]
if subjects:
    first_subject_path = os.path.join(KFALL_SENSOR_FOLDER, subjects[0])
    csv_files = [f for f in os.listdir(first_subject_path) if f.endswith(".csv")]
    print("subject folder:", subjects[0])
    print("example filenames:", csv_files[:5])

    if csv_files:
        sample = pd.read_csv(os.path.join(first_subject_path, csv_files[0]))
        print("csv columns:", list(sample.columns))
        print(sample.head())
else:
    print("no subject folders found under", KFALL_SENSOR_FOLDER)

print()
print("---- KFall label data ----")
# not 100% sure yet if label_data_new has one xlsx per subject directly,
# or subject subfolders too - just walk through and grab the first xlsx
label_file_found = None
for root, dirs, files in os.walk(KFALL_LABEL_FOLDER):
    for f in files:
        if f.endswith(".xlsx"):
            label_file_found = os.path.join(root, f)
            break
    if label_file_found:
        break

if label_file_found:
    print("example label file:", label_file_found)
    labels = pd.read_excel(label_file_found)
    print("label columns:", list(labels.columns))
    print(labels.head())
else:
    print("no xlsx label files found under", KFALL_LABEL_FOLDER)

print()
print("---- FallAllD ----")
if os.path.exists(FALLALLD_PICKLE):
    df = pd.read_pickle(FALLALLD_PICKLE)
    print("columns:", list(df.columns))
    print(df.head())
    print("unique ActivityID values:", df["ActivityID"].unique())
else:
    print("pickle file not found, did you run FallAllD's own conversion tool first?")

print()
print("---- URFD ----")
urfd_files = [f for f in os.listdir(URFD_FOLDER) if f.endswith(".csv")]
print("example files:", urfd_files[:10])
if urfd_files:
    sample = pd.read_csv(os.path.join(URFD_FOLDER, urfd_files[0]))
    print("columns:", list(sample.columns))
    print(sample.head())
