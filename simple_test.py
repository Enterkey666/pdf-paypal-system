#!/usr/bin/env python3
"""
Simple syntax test
"""

import os
import sys

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

print("Testing Python syntax...")

try:
    # Test database module syntax
    with open('database.py', 'r') as f:
        database_code = f.read()
    compile(database_code, 'database.py', 'exec')
    print("✓ database.py syntax OK")
except SyntaxError as e:
    print(f"✗ database.py syntax error: {e}")
    sys.exit(1)

try:
    # Test auth module syntax
    with open('auth.py', 'r') as f:
        auth_code = f.read()
    compile(auth_code, 'auth.py', 'exec')
    print("✓ auth.py syntax OK")
except SyntaxError as e:
    print(f"✗ auth.py syntax error: {e}")
    sys.exit(1)

print("✓ All syntax tests passed")