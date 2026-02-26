import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_github_issue_creation():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN not found in .env")
        return

    owner = "KataDavidXD"
    repo = "GithubAutoLark"
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    data = {
        "title": "[TEST] API Connection Test",
        "body": "This is a test issue created via API to verify token permissions and connectivity.\n\n- Sent from Cursor",
        "labels": ["test", "automated"]
    }
    
    try:
        print(f"Sending POST request to {url}...")
        response = requests.post(url, headers=headers, json=data)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 201:
            print("Success! Issue created.")
            print(f"Issue URL: {response.json().get('html_url')}")
        else:
            print("Failed to create issue.")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_github_issue_creation()
