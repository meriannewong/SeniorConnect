import tensorflow as tf
from tensorflow import keras
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVED_MODELS_DIR = os.path.join(BASE_DIR, "saved_models")

model = keras.models.load_model(os.path.join(SAVED_MODELS_DIR, "fall_mlp.keras"))

converter = tf.lite.TFLiteConverter.from_keras_model(model)
# no converter.optimizations / representative_dataset here on purpose -
# this stays a plain float32 model for Hailo's DFC to parse and quantize itself
tflite_model = converter.convert()

out_path = os.path.join(SAVED_MODELS_DIR, "fall_mlp_float32.tflite")
with open(out_path, "wb") as f:
    f.write(tflite_model)

print("saved float32 model to", out_path)
print("this is the file to feed into the Hailo Dataflow Compiler (parse stage)")

interpreter = tf.lite.Interpreter(model_path=out_path)
interpreter.allocate_tensors()
print("input details:", interpreter.get_input_details())
print("output details:", interpreter.get_output_details())
