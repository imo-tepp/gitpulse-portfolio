import os
import json
import redis
import requests
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

# Load configurations globally
load_dotenv()

app = FastAPI(title="GitPulse RateLimit Gateway")

# Hook up to the local high-speed Docker memory cache
try:
    cache = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    cache.ping()
    print("Infrastructure Handshake: Connected to local Docker Redis container!")
except redis.ConnectionError:
    print("Critical Infrastructure Error: Could not reach the Redis Docker container. Ensure Docker Desktop is active.")
    cache = None

@app.get("/")
def read_root():
    return {"status": "online", "gateway": "GitPulse Proxy Active"}

@app.get("/proxy/{owner}/{repo}")
def get_repository_data(owner: str, repo: str):
    """
    Acts as a secure reverse-proxy gateway. It intercepts requests,
    checks the local high-speed memory cache, and handles outbound traffic.
    """
    cache_key = f"repo:{owner}:{repo}"

    # 1. Look inside the local Docker cache first to prevent outbound network calls
    if cache:
        cached_data = cache.get(cache_key)
        if cached_data:
            print(f"Cache Hit! Serving structural data for {owner}/{repo} directly from Docker memroy.")
            return json.loads(cached_data)

    # 2. Cache Miss: We must make an outbound request to GitHub
    print(f"Cache Miss. Forwarding outbound request to GitHub API for {owner}/{repo}...")

    # Using your precise, fixed REST architecture layout string
    target_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GitPulse-Gateway-Proxy"
    }

    # Securely append your token if you have one configured in .env
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"

    response = requests.get(target_url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Remote server rejected proxy request.")

    repo_data = response.json()

    # 3. Store the result inside Docker Redis memory for 60 seconds to absorb high-frequency spam
    if cache:
        cache.setex(cache_key, 60, json.dumps(repo_data))
        print(f"Saved {owner}/{repo} data to local Docker memory store (60s TTL active).")

    return repo_data