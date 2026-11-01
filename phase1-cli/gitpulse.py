import os
import sys
import requests
from dotenv import load_dotenv

#load variables from the local .env file
load_dotenv()


def audit_repo_files(repo_owner, repo_name, headers):
    """
    Scans the repository file layout for DevOps hygiene and secret leakage.
    """
    print("Auditing repository file tree for compliance...")

    #Exact file tree routing format
    content_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents"

    try:
        response = requests.get(content_url, headers=headers)

        if response.status_code != 200:
            print("Unable to scan file contents (repository might be empty or private).")
            print(response.status_code)
            if response.status_code == 403:
                print("Tip: Your token is active, but it lacks the required 'Contents: Read' scope permission layout.")
            return

        files = response.json()

        # Track items we want to evaluate
        has_readme = False
        has_gitignore = False
        secret_leak_detected = False

        for file in files:
            file_name = file.get("name", "").lower()

            # Check for essential project documentation
            if "readme" in file_name:
                has_readme = True
            if "gitignore" in file_name:
                has_gitignore = True

            # Check for high-risk environmental exposures
            if file_name in [".env", "config.json", "secrets.yaml", "credentials.json"]:
                secret_leak_detected = True
                print(f"SECURITY ALERT: Exposed credential file found in source control: '{file.get('name')}'!")

        print("\n--- [ HYGIENE RESULTS ] ---")
        print(f"README Document: {'Present' if has_readme else 'Missing (Bad for portfolio!)'}")
        print(f"Gitignore Rules: {'Present' if has_gitignore else 'Missing (Risks environment pollution!)'}")
        if not secret_leak_detected:
            print("Secret Leak Check: Passed (No raw credentials found in root directory).")

    except Exception as e:
        print(f"File hygiene scan failed: {e}")

def check_repo_health(repo_owner, repo_name):
    """
    Connects to the GitHub API and audits a repository for basic configurations
    """
    print(f"Analyzing repository: {repo_owner}/{repo_name}...")

    # Set up requests headers and pull token if available
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GitPulse-App"
    }
    token = os.getenv("GITHUB_TOKEN")

    if token and "your_github_token" not in token and token.strip() != "":
        headers["Authorization"] = f"Bearer {token.strip()}"
        print("Authenticated via local system token.")
    else:
        print ("Running unauthenticated. Rate limits will be heavily restricted.")

    # Query the main repository endpoint
    api_url = f"http://127.0.0.1:8000/proxy/{repo_owner}/{repo_name}"

    try:
        response = requests.get(api_url, headers=headers)

        # Handle common HTTP status codes cleanly
        if response.status_code == 404:
            print(f"Error: The repository '{repo_owner}/{repo_name}' could not be found.")
            return
        elif response.status_code !=200:
            print(f"Error: API request failed with status code {response.status_code}")
            return

        repo_data = response.json()

        # Pull core metrics
        stars = repo_data.get("stargazers_count", 0)
        has_issues = repo_data.get("has_issues", False)

        license_info = repo_data.get("license")
        license_name = license_info.get("name") if license_info else "Missing License File"

        print("\n--- [ AUDIT REPORT ] ---")
        print(f"Stars: {stars}")
        print(f"Issues Enabled: {'Yes' if has_issues else 'No'}")
        print(f"License: {license_name}")
        print("-" * 24)

        #Trigger the hygiene check automatically
        audit_repo_files(repo_owner, repo_name, headers)

    except requests.exceptions.RequestException as e:
        print(f"Network connectivity error: {e}")

if __name__ == "__main__":
    # Test using a highly popular open-source project
    check_repo_health("psf", "requests")