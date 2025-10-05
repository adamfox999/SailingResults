#!/usr/bin/env python3
"""Test the reference endpoint locally."""
import os
import sys

# Load environment from .env file
from pathlib import Path
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()

# Add parent to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from app.main import reference
    
    print("Calling reference endpoint...")
    result = reference()
    
    print(f"✓ Success!")
    print(f"  Classes: {len(result['classes'])}")
    print(f"  Class Options: {len(result['classOptions'])}")
    print(f"  Fin Codes: {len(result['finCodes'])}")
    
    # Show first few class options
    print("\nFirst 5 class options:")
    for opt in result['classOptions'][:5]:
        print(f"  {opt['key']} -> {opt['label']}")
    
    # Check for DART/SPRINT
    print("\nDART/SPRINT check:")
    dart_sprint_options = [opt for opt in result['classOptions'] if 'DART' in opt['label'] or 'SPRINT' in opt['label']]
    for opt in dart_sprint_options[:5]:
        print(f"  {opt['key']} -> {opt['label']}")
    
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
