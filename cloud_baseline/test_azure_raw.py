import requests

AZURE_URL = "https://fallmlp-mewong3.azurewebsites.net/predict"

# same real feature row test_local.py used successfully against the local API
features = [-0.057925, 0.0037788060283639, -0.047, -0.067, -1.00646,
            0.0046923767964646, -0.993, -1.02, -0.0101399999999999,
            0.0048322251603169, 0.003, -0.022, 1.0081950083938311,
            0.004725468205627, 1.0219065515006742]

print("sending request to", AZURE_URL)
r = requests.post(AZURE_URL, json={"features": features}, timeout=60)

print()
print("status code:", r.status_code)
print()
print("raw response text (first 2000 chars):")
print(r.text[:2000])
