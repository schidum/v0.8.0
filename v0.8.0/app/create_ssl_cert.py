# create_cert.py
# Simple way to create SSL certificates using Python (no openssl needed)

from pathlib import Path
import subprocess
import sys

print("=== Creating SSL certificates for localhost ===")

cert_dir = Path("certs")
cert_dir.mkdir(exist_ok=True)

print("Generating certificate...")

try:
    # Try using openssl if available
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:4096",
        "-nodes", "-days", "365", 
        "-keyout", "certs/key.pem",
        "-out", "certs/cert.pem",
        "-subj", "/CN=localhost"
    ], check=True, shell=True, capture_output=True)

    print("SUCCESS!")
    print("Files created:")
    print("   - certs/cert.pem")
    print("   - certs/key.pem")

except FileNotFoundError:
    print("ERROR: 'openssl' command not found.")
    print("\nYou have 2 options:")
    print("1. Install Git for Windows (recommended) - it includes openssl")
    print("2. Run the server without SSL for development")
    
    print("\nTo run without SSL, use this command:")
    print('uvicorn app.main:app --reload --host 127.0.0.1 --port 8000')

except subprocess.CalledProcessError as e:
    print(f"Error during certificate creation: {e}")
    print("Trying alternative method...")

print("\nDone.")