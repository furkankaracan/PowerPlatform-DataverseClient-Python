---
description: "Use when writing Python code that connects to Dataverse — authentication, credentials, client setup, environment variables, .env file. Covers ClientSecretCredential pattern for this project."
applyTo: "/*.py"
---

# Dataverse Authentication — Project Convention

## Credential Pattern

This project uses `ClientSecretCredential` (service principal) for authentication, with all secrets loaded from a `.env` file via `python-dotenv`.

```python
import os
from dotenv import load_dotenv
from azure.identity import ClientSecretCredential
from PowerPlatform.Dataverse.client import DataverseClient

load_dotenv()

credential = ClientSecretCredential(
    tenant_id=os.getenv("AZURE_TENANT_ID"),
    client_id=os.getenv("AZURE_CLIENT_ID"),
    client_secret=os.getenv("AZURE_CLIENT_SECRET"),
)

client = DataverseClient(os.getenv("DATAVERSE_URL"), credential)
```

## Required `.env` Variables

```env
DATAVERSE_URL=https://yourorg.crm.dynamics.com
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
```

## Rules

- Always use `load_dotenv()` at the top of example scripts — never hardcode credentials
- The `.env` file is gitignored; never commit it
- Use `ClientSecretCredential` (not `InteractiveBrowserCredential`) for all example scripts in this project
- Always use `os.getenv("DATAVERSE_URL")` for the environment URL — never hardcode it
- Use the context manager pattern (`with DataverseClient(...) as client:`) for automatic cleanup
