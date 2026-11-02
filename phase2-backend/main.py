import os
import json
import time
import redis
import requests
from fastapi import FastAPI, HTTPException, Request, status
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

def check_rate_limit(client_ip: str) -> bool:
    """
    Implements a Sliding Window Rate Limiter inside Docker Redis memory.
    Limits each unique IP address to 5 requests per minute.
    Returns True if allowed, False if rate-limited
    """
    if not cache:
        return True # Fallback safely if database is offline

    rate_limit_key = f"ratelimit: {client_ip}"
    current_time = time.time()
    one_minute_ago = current_time - 60

    # Create a pipeline to execute multiple Redis commands in a single network round-trip
    pipeline = cache.pipeline()

    # 1. Remove request timestamps older than 60 seconds
    pipeline.zremrangebyscore(rate_limit_key, 0, one_minute_ago)
    # 2. Add the current unique request timestamp to the sorted set
    pipeline.zadd(rate_limit_key, {str(current_time): current_time})
    # 3. Count how many total requests this IP has made within the active window
    pipeline.zcard(rate_limit_key)
    # 4. Set the tracking key to expire in 60 seconds so it cleans itself up
    pipeline.expire(rate_limit_key, 60)

    # Execute commands and pull the result from step 3 (index 2 in responses)
    responses = pipeline.execute()
    request_count = responses[2]

    # Block the request if it exceeds our threshold
    if request_count > 5:
        return False

    return True

@app.get("/")
def read_root():
    return {"status": "online", "gateway": "GitPulse Proxy Active"}

@app.get("/proxy/{owner}/{repo}")
def get_repository_data(owner: str, repo: str, request: Request):
    """
    Sticks strictly to the custom/proxy route. Validates traffic rates,
    evalautes local memory cache, and handles outbound GitHub connections.
    """
    client_ip = request.client.host
    print(f"Custom Proxy Triggered by {client_ip} for: {owner}/{repo}")

    # --- [ PROXIED FIREWALL CHECK ] ---
    if not check_rate_limit(client_ip):
        print(f"FIREWALL ALERT: Rate Limit Exceeded by IP: {client_ip}! Blocking request.")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Gateway restriction: Maximum 5 requests per minute."
        )

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
    if token and "your_github_token" not in token and token.strip() != "":
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