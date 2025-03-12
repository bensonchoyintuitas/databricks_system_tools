import requests
import subprocess
import json
import csv
from pathlib import Path
import time

# Constants
DB_RESOURCE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
CSV_FILE = Path("output/workspace_owners.csv")
ENV_FILE = Path(".env")

def get_account_id():
    """Read account ID from .env file in KEY=value format."""
    try:
        with open(ENV_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('ACCOUNT_ID='):
                    return line.split('=', 1)[1].strip('"\'')
            print("❌ Error: ACCOUNT_ID not found in .env file")
            return None
    except FileNotFoundError:
        print(f"❌ Error: {ENV_FILE} not found. Please create the file with your Databricks Account ID")
        return None
    except Exception as e:
        print(f"❌ Error reading token file: {e}")
        return None

def get_azure_ad_token():
    """Fetch an Azure AD token for Databricks Accounts API using Azure CLI."""
    try:
        result = subprocess.run(
            ["az", "account", "get-access-token", "--resource", DB_RESOURCE],
            capture_output=True, text=True, check=True
        )
        return json.loads(result.stdout).get("accessToken")
    except Exception as e:
        print(f"⚠️ Warning: Failed to get Azure AD token. Error: {e}")
        return None

def get_workspaces(account_id, access_token):
    """Retrieve all Databricks workspaces for a given account."""
    url = f"https://accounts.azuredatabricks.net/api/2.0/accounts/{account_id}/workspaces"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # ✅ Print response to debug
        print("🔎 Raw API Response:", response.text)

        # ✅ Check if response is a list instead of a dictionary
        json_response = response.json()
        if isinstance(json_response, list):
            print("⚠️ API returned a list instead of a dictionary. Handling accordingly.")
            return json_response  # Directly return if it's a list

        return json_response.get("workspaces", [])

    except requests.exceptions.RequestException as e:
        print(f"❌ Error retrieving workspaces: {e}")
        return []


def get_workspace_admins(workspace_url, access_token):
    """Fetch workspace admins from Databricks SCIM API and resolve user emails."""
    url = f"{workspace_url}/api/2.0/preview/scim/v2/Groups"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            groups = response.json().get("Resources", [])
            for group in groups:
                if group.get("displayName") == "admins":
                    admin_ids = [user["value"] for user in group.get("members", [])]
                    
                    # ✅ Convert admin IDs to emails
                    admin_emails = [get_user_email(workspace_url, access_token, admin_id) for admin_id in admin_ids]
                    return admin_emails
        elif response.status_code == 403:
            print(f"⚠️ SCIM API access denied for {workspace_url}. Ensure SCIM is enabled.")
        else:
            print(f"⚠️ Warning: Unable to retrieve admins for {workspace_url} - Status Code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error retrieving workspace admins: {e}")

    return []

def get_user_email(workspace_url, access_token, user_id):
    """Fetch user email or detect if the user is deleted."""
    url = f"{workspace_url}/api/2.0/preview/scim/v2/Users/{user_id}"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            user_data = response.json()

            # ✅ Check if the user is a service principal
            if "schemas" in user_data and "urn:ietf:params:scim:schemas:core:2.0:ServicePrincipal" in user_data["schemas"]:
                return f"Service Principal: {user_data.get('displayName', 'Unknown')}"
            
            return user_data.get("userName", user_id)  # ✅ Return email if available

        elif response.status_code == 404:
            print(f"⚠️ Warning: User {user_id} not found (may be deleted).")
            return f"Deleted User: {user_id}"  # ✅ Handle missing users gracefully

    except requests.exceptions.RequestException as e:
        print(f"❌ Error retrieving user email for {user_id}: {e}")

    return user_id  # Fallback to user ID if no data is found




def save_to_csv(data):
    """Save workspace admin data to a CSV file (flattened format)."""
    CSV_FILE.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists

    with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["workspace_id", "workspace_name", "workspace_url", "admin_email"])
        writer.writerows(data)

    print(f"\n✅ CSV file saved: {CSV_FILE}")

def main():
    print("🚀 Fetching Databricks workspaces...")
    access_token = get_azure_ad_token()
    if not access_token:
        print("❌ No valid authentication token found. Exiting.")
        return

    account_id = get_account_id()
    if not account_id:
        print("❌ No valid account ID found. Exiting.")
        return

    workspaces = get_workspaces(account_id, access_token)
    if not workspaces:
        print("❌ No workspaces found. Exiting.")
        return

    all_data = []
    print("\n🔎 Retrieving workspace owners...\n")

    for workspace in workspaces:
        print(f"🔎 Debug Workspace Data: {workspace}")  # Debugging

        # Extract workspace details
        workspace_id = workspace.get("workspace_id")
        workspace_name = workspace.get("workspace_name", "UNKNOWN")
        deployment_name = workspace.get("deployment_name", "")

        # ✅ Construct the workspace URL dynamically
        workspace_url = f"https://{deployment_name}.azuredatabricks.net"

        print(f"🔹 Checking workspace: {workspace_name} ({workspace_id}) - {workspace_url}")

        # Proceed only if workspace_url exists
        if not workspace_url:
            print(f"⚠️ Warning: Workspace {workspace_name} ({workspace_id}) is missing 'workspace_url'. Skipping...")
            continue

        # Get workspace admins
        admins = get_workspace_admins(workspace_url, access_token)

        # Store results in CSV format (flattened)
        if admins:
            for admin in admins:
                all_data.append([workspace_id, workspace_name, workspace_url, admin])
            print(f"   ✅ Owners: {', '.join(admins)}")
        else:
            all_data.append([workspace_id, workspace_name, workspace_url, "No Owners Found"])
            print(f"   ⚠️ No owners found!")

        # **Rate limit handling** to avoid API throttling
        time.sleep(1)

    # Save results to CSV
    save_to_csv(all_data)
    print("\n✅ Done.")

if __name__ == "__main__":
    main()
