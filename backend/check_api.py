import json
import httpx

response = httpx.get("http://127.0.0.1:8000/reference")
data = response.json()

print(f"Total classOptions: {len(data['classOptions'])}")
print("\nDart/Sprint classes:")
for opt in data['classOptions']:
    if 'DART' in opt['label'] or 'SPRINT' in opt['label']:
        print(f"  {opt['key']} -> {opt['label']}")

print("\n'SPRINT 15' in classes dict:", 'SPRINT 15' in data['classes'])
print("'DART 15' in classes dict:", 'DART 15' in data['classes'])
print("'DART 15 / SPRINT 15' in classes dict:", 'DART 15 / SPRINT 15' in data['classes'])
