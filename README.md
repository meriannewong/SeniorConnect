# SeniorConnect

Edge-AI fall detection + caregiver alert dashboard, MSc dissertation project.

## Folder structure

```
seniorconnect/
├── data/                  # raw datasets go here (not written to github,
│   ├── KFall/             #   too big + licensing), see build_log.md for
│   ├── FallAllD/          #   where each one was downloaded from
│   └── URFD/
│
├── preprocessing/
│   ├── check_columns.py   # run this first, prints real column names
│   └── preprocess.py      # windows the data + extracts features ->
│                           #   saves to results/processed_features.csv
│
├── model/
│   ├── train_model.py     # trains the fall/not-fall classifier
│   └── convert_to_tflite.py
│
├── edge_deployment/
│   ├── hailo_notes.md     # steps + commands for compiling to .hef
│   └── benchmark_edge.py  # runs on the Pi, times inference
│
├── cloud_baseline/
│   └── benchmark_cloud.py # cloud comparison point for the benchmark
│
├── dashboard/
│   ├── app.py             # Flask app, caregiver-facing
│   └── templates/
│
├── results/                # processed_features.csv, benchmark numbers,
│   └── plots/               #   plots for the report go here
│
├── notes/
│   └── build_log.md        # running notes, doubles as report material
│
└── requirements.txt
```

## Run order (roughly)

1. `preprocessing/check_columns.py` - check the real dataset format first
2. `preprocessing/preprocess.py` - build `results/processed_features.csv`
3. `model/train_model.py` - get a working baseline classifier
4. `model/convert_to_tflite.py` - shrink it down for the Pi
5. Hailo compiler steps (see `edge_deployment/hailo_notes.md`) - outside
   of python, needs the Hailo SDK
6. `edge_deployment/benchmark_edge.py` - on the Pi, measure latency
7. `cloud_baseline/benchmark_cloud.py` - comparison numbers
8. `dashboard/app.py` - caregiver-facing alert dashboard

Most of these are still empty skeletons with a comment saying what needs
to go in them - filling them in one at a time, in roughly this order.
