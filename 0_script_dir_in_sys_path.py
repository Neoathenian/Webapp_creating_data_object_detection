import sys
import os
# Set up the script directory and ensure it's in sys.path
script_directory = os.path.dirname(os.path.abspath(__file__))
if script_directory not in sys.path:
    sys.path.append(script_directory)

from dotenv import load_dotenv


import argparse
import uvicorn

# Import AFTER env is loaded

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8086)
    ap.add_argument("--env", type=str, default="dev")

    args = ap.parse_args()

    # Load .env relative to this script so it works regardless of CWD
    env_path = os.path.join(script_directory, f"env.{args.env}")
    load_dotenv(env_path, override=True)

    # Normalize GOOGLE_APPLICATION_CREDENTIALS to POSIX/absolute path
    gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if gac:
        fixed = gac.replace("\\", "/")
        if not os.path.isabs(fixed):
            fixed = os.path.join(script_directory, fixed)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = fixed

    # Ensure TLS trust store is available for Cloud SQL connector / aiohttp
    if not os.getenv("SSL_CERT_FILE") or not os.path.exists(os.getenv("SSL_CERT_FILE", "")):
        try:
            import certifi  # type: ignore

            cert_path = certifi.where()
            os.environ.setdefault("SSL_CERT_FILE", cert_path)
            os.environ.setdefault("REQUESTS_CA_BUNDLE", cert_path)
        except Exception:
            pass

    #This is the last thing to do because first we need the secrets imported
    from app import app
    uvicorn.run(app, host="0.0.0.0", port=args.port)
