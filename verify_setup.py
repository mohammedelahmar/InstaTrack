"""
Verify your InstaTrack setup.
Run this script to check if your environment is ready.
"""
import sys
import os
import importlib.util
from pathlib import Path

def check_python_version():
    major, minor = sys.version_info[:2]
    print(f"[*] Python Version: {major}.{minor}", end=" ")
    if major < 3 or (major == 3 and minor < 10):
        print("[FAIL] (Requires 3.10+)")
        return False
    print("[OK]")
    return True

def check_imports():
    required = ["flask", "pymongo", "instagrapi", "dotenv", "requests"]
    missing = []
    print("[*] Checking Dependencies:", end=" ")
    for pkg in required:
        if not importlib.util.find_spec(pkg):
            missing.append(pkg)
    
    if missing:
        print(f"[FAIL] Missing: {', '.join(missing)}")
        print("    -> Run: pip install -r requirements.txt")
        return False
    print("[OK] All found")
    return True

def check_env_file():
    possible_paths = [Path(".env"), Path("config/.env")]
    env_path = None
    
    print(f"[*] Checking .env file:", end=" ")
    for p in possible_paths:
        if p.exists():
            env_path = p
            break
            
    if not env_path:
        print("[FAIL] Not found")
        print("    -> Action: Copy .env.example to .env (or config/.env) and fill it in.")
        return False
    print(f"[OK] Found at {env_path}")
    
    # Check key variables
    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    required_vars = ["TARGET_ACCOUNTS"]
    missing_vars = [v for v in required_vars if v not in content]
    
    if missing_vars:
        print(f"    [WARN] Warning: {', '.join(missing_vars)} might be missing in .env")
    else:
        print("    [OK] TARGET_ACCOUNTS looks present")
    return True

def main():
    print("=== InstaTrack Setup Verifier ===\n")
    ok_py = check_python_version()
    ok_deps = check_imports()
    ok_env = check_env_file()
    
    print("\n" + "-"*30)
    if ok_py and ok_deps and ok_env:
        print("[SUCCESS] Your environment looks ready!")
        print("   -> Run: python main.py web")
    else:
        print("[ISSUES FOUND] Please fix the errors above.")

if __name__ == "__main__":
    main()
