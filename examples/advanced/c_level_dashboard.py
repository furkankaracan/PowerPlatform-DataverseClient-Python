# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
C-Level Sales Dashboard — Dataverse Example
============================================

What this script does:
  1. Queries Dataverse for accounts whose total opportunity pipeline value is at least £1,000
  2. Builds a 4-panel executive dashboard (bar chart, pie, scatter, donut) and saves it as PNG
  3. Sends a Dataverse in-app notification to the current user with the top 5 accounts

Reference:
  Opportunity entity: https://learn.microsoft.com/en-us/dynamics365/developer/reference/entities/opportunity
  In-App Notifications: https://learn.microsoft.com/en-us/power-apps/developer/model-driven-apps/clientapi/send-in-app-notifications

Prerequisites (install if missing):
  pip install pandas matplotlib

Usage:
  python examples/advanced/c_level_dashboard.py
"""

# ── Standard library ──────────────────────────────────────────────────────────
import os

# ── Third-party: auth ─────────────────────────────────────────────────────────
from dotenv import load_dotenv                   # Reads variables from .env file
from azure.identity import ClientSecretCredential

# ── SDK ───────────────────────────────────────────────────────────────────────
from PowerPlatform.Dataverse.client import DataverseClient

# ── Dashboard logic lives in the src extension module ─────────────────────────
from PowerPlatform.Dataverse.extensions.sales_dashboard import (
    AccountSalesDashboard,          # Class: fetch data + render charts
    send_top_accounts_notification,  # Function: post in-app notification
)

# Load all variables defined in .env into os.environ
load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Run the C-Level dashboard end-to-end."""
    print("C-Level Sales Dashboard")
    print("=" * 55)

    # Read credentials from environment / .env into named variables.
    # os.getenv() returns str | None, so we validate before passing them on.
    tenant_id     = os.getenv("AZURE_TENANT_ID")
    client_id     = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    dataverse_url = os.getenv("DATAVERSE_URL")

    # Fail early with a clear message if any variable is missing from .env
    if not all([tenant_id, client_id, client_secret, dataverse_url]):
        raise EnvironmentError(
            "Missing required environment variables. "
            "Add AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, "
            "and DATAVERSE_URL to your .env file."
        )

    # After the check above, the variables are guaranteed to be non-None strings.
    # assert tells Pylance to treat them as str instead of str | None.
    assert tenant_id and client_id and client_secret and dataverse_url

    # Build the credential from .env variables (see dataverse-auth instructions)
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )

    # The 'with' block opens an HTTP connection pool and closes it cleanly when done
    with DataverseClient(dataverse_url, credential) as client:

        # ── Step 1: Query + aggregate ─────────────────────────────────────────
        print("\n[1/3] Fetching account sales data...")
        dashboard = AccountSalesDashboard(client)
        df = dashboard.fetch_accounts_with_orders()

        if df.empty:
            print("\nNo qualifying accounts found. Exiting.")
            return

        # Show a quick preview in the terminal
        print("\n  Preview (top 10 rows):")
        preview = df.head(10)[["account_name", "total_amount", "order_count"]].copy()
        preview["total_amount"] = preview["total_amount"].apply(lambda v: f"${v:,.0f}")
        print(preview.to_string(index=False))

        # ── Step 2: Create dashboard charts ──────────────────────────────────
        print("\n[2/3] Creating C-Level dashboard charts...")
        dashboard.create_dashboard(df, show_interactive=True)

        # ── Step 3: Send in-app notification ─────────────────────────────────
        recipient = input(
            "\n  Enter recipient email (leave blank to notify yourself): "
        ).strip() or None
        print("\n[3/3] Sending in-app notification for top 5 accounts...")
        send_top_accounts_notification(client, df, recipient_email=recipient)

    print("\nDone.")


if __name__ == "__main__":
    main()
