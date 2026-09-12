# Hailo deployment notes

Getting a model onto the Pi 5 + Hailo-8 isn't just a python script, it goes
through the Hailo Dataflow Compiler as a separate step. Writing this down
here so I don't forget the order:

1. Train model -> saved as .h5 (model/train_model.py)
2. Convert .h5 -> .tflite (model/convert_to_tflite.py)
3. Use Hailo Dataflow Compiler (runs on a normal PC, not the Pi itself) to
   turn .tflite into a .hef file - this step needs the Hailo SDK installed
   and probably a calibration dataset (small sample of the training data)
4. Copy the .hef file onto the Pi 5
5. Run benchmark_edge.py on the Pi to load the .hef and time the inference

TODO: fill in the actual hailomz / hailo compiler commands once I've
installed the SDK and know the exact syntax for this project.
