"""
webhook_server.py

A simple Flask server to handle GitHub webhook events for PR review approvals and pushes to main.
It verifies webhook signatures using a shared secret and triggers a test script when appropriate.

Endpoints:
- /webhook: Handles pull request review events.
- /pushhook: Handles push events.
"""

from flask import Flask, request
import subprocess
import hmac
import hashlib
import os

app = Flask(__name__)
GITHUB_SECRET = b'supersecret123'  # must match GitHub webhook secret, 
                                   # should be move to .env or config file !!

#### all helpers neet to be in separte folders #####
def verify_signature(payload, signature):
    """
    Verify the HMAC SHA256 signature of the incoming webhook payload.

    Args:
        payload (bytes): The raw request data.
        signature (str): The signature from the 'X-Hub-Signature-256' header.

    Returns:
        bool: True if the signature is valid, False otherwise.
    """
    mac = hmac.new(GITHUB_SECRET, msg=payload, digestmod=hashlib.sha256)
    return hmac.compare_digest("sha256=" + mac.hexdigest(), signature)

def valid_github_signature(request):
    """
    Verifies the GitHub webhook signature in the request.

    Args:
        request (Flask.Request): The incoming Flask request object.

    Returns:
        bool: True if the signature is valid, False otherwise.
    """
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        print("[!] Missing signature header")
        return False
    return verify_signature(request.data, signature)


def OnPushWBTeam(payload):
    """
    Placeholder for handling pushes to billing-main or weight-main.
    Args:
        payload (dict): The full GitHub webhook payload.
    """
    ######### EXAMPLE LOGIC, NOT TESTED #########
    import os, datetime, subprocess

    ref = payload.get("ref", "")
    branch = ref.split("/")[-1]
    pusher = payload.get("pusher", {}).get("name", "unknown")
    repo = payload.get("repository", {}).get("full_name", "unknown")
    time_now = datetime.datetime.now().isoformat()
    commits = payload.get("commits", [])
    commit_msg = commits[0]["message"] if commits else "No commit message"

    log_path = f"/log/{branch}.log"
    os.makedirs("/log", exist_ok=True)

    with open(log_path, "a") as log:
        log.write(f"[{time_now}] Push to {branch} by {pusher} in {repo}\n")
        for commit in commits:
            log.write(f"- {commit['id'][:7]}: {commit['message']}\n")

    # Trigger host-side script, that runs the docker compose and the test inside it 
    try:
        subprocess.Popen(
            ["/bin/bash", "/host_scripts/run_tests.sh", branch],
            stdout=open(log_path, "a"),
            stderr=subprocess.STDOUT,
        )
        print(f"[+] DevTeam test started for {branch}")
    except Exception as e:
        print(f"[!] Failed to run tests: {e}")

    pass  # TODO: Add dev team script logic here

def OnPushDevBranch(payload):
    """
    Placeholder for handling pushes to dev branch.
    Args:
        payload (dict): The full GitHub webhook payload.
    """
    pass  # TODO: Add dev branch logic here, it is the acutal production branch


@app.route('/')
def home():
    """
    Basic health check endpoint.
    """
    return "hello from flask !"

@app.route('/pushhook', methods=['POST'])
def push_webhook():
    """
    Handle GitHub push webhook events.
    React only to billing-main, weight-main, main-devops, and dev branches.
    """

    if not valid_github_signature(request):
        return "Invalid signature", 403

    data = request.json
    ref = data.get("ref", "")  # e.g., 'refs/heads/main-devops'
    branch = ref.split("/")[-1]
    pusher = data.get("pusher", {}).get("name", "unknown")
    repo = data.get("repository", {}).get("full_name", "unknown")
    commits = data.get("commits", [])
    commit_msg = commits[0]["message"] if commits else "No commit message"

    print(f"[+] Push to branch: {branch}")

    if branch in ["billing-main", "weight-main", "main-devops", "dev"]:
        print(f"[Webhook] CI triggered for {branch}")
        subprocess.Popen(
            ["/bin/bash", "./run_tests.sh", branch],
            env={
                **os.environ,
                "BRANCH": branch,
                "PUSHER": pusher,
                "REPO": repo,
                "COMMIT_MSG": commit_msg,
            }
        )
        return f"{branch} CI started", 200

    elif branch == "dev":
        print(f"[Webhook] CI triggered for {branch}")
        subprocess.Popen(
            ["/bin/bash", "./run_team_ci.sh", branch]
        )
        return f"{branch} CI started", 200

    print("[~] Push to other branch ignored.")
    return "Push webhook ignored", 200

if __name__ == '__main__':
    # Run the Flask app on all interfaces, port 8080
    app.run(host='0.0.0.0', port=8080)
