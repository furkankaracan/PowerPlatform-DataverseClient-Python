# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Seed Opportunities — Dataverse Example
=======================================

Idempotently seeds 10 Accounts, 2 Contacts, 10 Opportunities and their
product line items for development and testing purposes, all themed around
the Dunder Mifflin Paper Company (Scranton, PA).

Each record matches the shape of real production data but has
``statecode=0`` (Open) so it can be used for fresh test runs.  Re-running
the script is safe — accounts and contacts are find-or-created by name/fullname
so they are never duplicated.

All reference data is resolved from the API at runtime — no fixed GUIDs or
environment variables are required beyond the authentication credentials:

  - Currency    : first GBP transaction currency (isocurrencycode='GBP')
  - Price List  : first active price list (statecode=0)
  - Account     : seeded from ``_ACCOUNTS`` catalogue (find-or-create by name)
  - Contact     : seeded from ``_CONTACTS`` catalogue (find-or-create by fullname)
  - Owner       : service-principal user resolved via WhoAmI()
  - Products    : looked up by productnumber (must be Active, i.e. published)

Budget amounts are fixed per scenario and reflect realistic quantities × unit prices.

Usage
-----
  python examples/advanced/seed_opportunities.py

Prerequisites
-------------
  pip install python-dotenv azure-identity
"""

# ── Standard library ──────────────────────────────────────────────────────────
import os
from typing import Optional

# ── Third-party ───────────────────────────────────────────────────────────────
import requests as _req
from dotenv import load_dotenv
from azure.identity import ClientSecretCredential

# ── SDK ───────────────────────────────────────────────────────────────────────
from PowerPlatform.Dataverse.client import DataverseClient

load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _http_headers(client: DataverseClient) -> tuple[str, dict]:
    """Return (base_url, OData auth headers) for raw HTTP calls."""
    base_url = client._base_url
    token = client.auth._acquire_token(f"{base_url}/.default").access_token
    return base_url, {
        "Authorization":    f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version":    "4.0",
        "Accept":           "application/json",
        "Content-Type":     "application/json; charset=utf-8",
    }


def _get_first(base_url: str, headers: dict, entity_set: str, select: str,
               filter_: Optional[str] = None) -> Optional[dict]:
    """Return the first record from ``entity_set``, or None if empty."""
    params: dict = {"$select": select, "$top": "1"}
    if filter_:
        params["$filter"] = filter_
    resp = _req.get(f"{base_url}/api/data/v9.2/{entity_set}", headers=headers, params=params)
    resp.raise_for_status()
    rows = resp.json().get("value", [])
    return rows[0] if rows else None


def _find_or_create(
    label: str,
    base_url: str,
    headers: dict,
    entity_set: str,
    id_field: str,
    filter_: str,
    create_fn,  # () -> str
) -> tuple[str, bool]:
    """
    Return ``(record_id, skipped)``.

    If a record matching ``filter_`` already exists the function returns its ID
    and ``skipped=True`` without touching Dataverse.  Otherwise it calls
    ``create_fn()`` to create the record and returns ``skipped=False``.
    """
    existing = _get_first(base_url, headers, entity_set, select=id_field, filter_=filter_)
    if existing:
        print(f"     [SKIP] {label} (already exists: {existing[id_field]})")
        return existing[id_field], True
    new_id: str = create_fn()
    print(f"     [NEW]  {label}: {new_id}")
    return new_id, False


# ── Seeded scenarios ──────────────────────────────────────────────────────────
# Ten Dunder Mifflin paper & office supply deals across all four BPF stages.
#
# account_name: resolved via accounts.name at runtime (binding omitted if not found)
# contact_name: resolved via contacts.fullname at runtime (None = skip lookup)
# salesstagecode: always 1 (only accepted value — "Default")
# salesstage:     0=Qualify  1=Develop  2=Propose  3=Close
_SCENARIOS = [
    {
        "name":         "Lackawanna County School District — annual paper supply (seed)",
        "description":  "Annual paper supply contract for 42 Lackawanna County schools covering the 2026–27 academic year.",
        "account_name": "Lackawanna County School District",
        "contact_name": None,
        "customerneed":      "Stock copy paper for 42 schools ahead of the new academic year.",
        "proposedsolution":  "Dunder Mifflin Copy Paper 20 lb — case pallet contract, quarterly delivery.",
        "currentsituation":  "Current supplier raised prices 15%; procurement is reviewing alternatives.",
        "stepname": "1-Qualify",
        "salesstagecode": 1,
        "salesstage": 0,  # Qualify
        "budget": 2_400,
        "products": [
            {"productnumber": "DM-CP20-CASE", "quantity": 50},
            {"productnumber": "DM-LP-PACK",   "quantity": 10},
        ],
    },
    {
        "name":         "Scranton Business Park — printer paper refresh (seed)",
        "description":  "Subscription supply of premium 24 lb copy paper to replace jam-prone recycled stock across all tenants.",
        "account_name": "Scranton Business Park",
        "contact_name": None,
        "customerneed":      "Replace low-grade recycled paper that jams Xerox printers.",
        "proposedsolution":  "Dunder Mifflin Premium 24 lb Bright White — 10-ream case subscription.",
        "currentsituation":  "Maintenance costs spiking due to paper jams; tenants are complaining.",
        "stepname": "1-Qualify",
        "salesstagecode": 1,
        "salesstage": 0,  # Qualify
        "budget": 1_200,
        "products": [
            {"productnumber": "DM-CP24-CASE", "quantity": 20},
        ],
    },
    {
        "name":         "Vance Refrigeration — office stationery bundle (seed)",
        "description":  "Consolidated stationery bundle for Vance Refrigeration — copy paper, envelopes, and legal pads under one vendor agreement.",
        "account_name": "Vance Refrigeration",
        "contact_name": "Bob Vance",
        "customerneed":      "Single vendor for all paper, envelopes, and notepads.",
        "proposedsolution":  "Dunder Mifflin Business Bundle: copy paper + legal pads + #10 envelopes.",
        "currentsituation":  "Bob Vance (Vance Refrigeration) wants to consolidate suppliers.",
        "stepname": "2-Develop",
        "salesstagecode": 1,
        "salesstage": 1,  # Develop
        "budget": 540,
        "products": [
            {"productnumber": "DM-CP20-CASE", "quantity": 10},
            {"productnumber": "DM-ENV10-BOX", "quantity":  5},
            {"productnumber": "DM-LP-PACK",   "quantity":  3},
        ],
    },
    {
        "name":         "Steamtown Mall — retail flyer print stock (seed)",
        "description":  "Weekly standing order for glossy 80 lb cover stock to produce in-store promotional flyers and tenant inserts.",
        "account_name": "Steamtown Mall",
        "contact_name": None,
        "customerneed":      "High-volume glossy brochure paper for weekly promotional flyers.",
        "proposedsolution":  "Dunder Mifflin Glossy Cover Stock 80 lb — standing weekly order.",
        "currentsituation":  "Current stock quality inconsistent; colours wash out on Sunday inserts.",
        "stepname": "2-Develop",
        "salesstagecode": 1,
        "salesstage": 1,  # Develop
        "budget": 600,
        "products": [
            {"productnumber": "DM-CS80G-REAM", "quantity": 30},
        ],
    },
    {
        "name":         "Cooper & Greene Law Firm — letterhead paper (seed)",
        "description":  "Premium cotton-bond letterhead supply agreement for the firm's rebranded corporate correspondence.",
        "account_name": "Cooper & Greene Law Firm",
        "contact_name": None,
        "customerneed":      "Premium cotton-bond letterhead stock for client correspondence.",
        "proposedsolution":  "Dunder Mifflin 25% Cotton Bond 28 lb — custom watermark option.",
        "currentsituation":  "Firm rebranding; existing letterhead stock depleted.",
        "stepname": "2-Develop",
        "salesstagecode": 1,
        "salesstage": 1,  # Develop
        "budget": 200,
        "products": [
            {"productnumber": "DM-CB28-REAM", "quantity": 15},
        ],
    },
    {
        "name":         "Dunder Mifflin Infinity — Sabre merger paper transition (seed)",
        "description":  "Internal fleet migration from Sabre paper stock to DM standard across all Scranton and satellite branches.",
        "account_name": "Dunder Mifflin",
        "contact_name": None,
        "customerneed":      "Migrate internal print fleet from Sabre paper to DM standard stock.",
        "proposedsolution":  "Dunder Mifflin Copy Paper 20 lb + cardstock assortment — all branches.",
        "currentsituation":  "Post-merger inventory audit revealed incompatible paper weights per site.",
        "stepname": "3-Propose",
        "salesstagecode": 1,
        "salesstage": 2,  # Propose
        "budget": 6_400,
        "products": [
            {"productnumber": "DM-CP20-CASE", "quantity": 100},
            {"productnumber": "DM-CS65-CASE", "quantity":  20},
        ],
    },
    {
        "name":         "Northeastern Pennsylvania Hospital — medical record paper (seed)",
        "description":  "HIPAA-compliant paper procurement for EHR printouts and patient-facing documentation across all departments.",
        "account_name": "Northeastern Pennsylvania Hospital",
        "contact_name": None,
        "customerneed":      "HIPAA-compliant laser paper for EHR printouts and patient forms.",
        "proposedsolution":  "Dunder Mifflin Medical Grade 20 lb — chlorine-free, acid-free certified.",
        "currentsituation":  "Procurement mandate to source domestic paper only from Q3.",
        "stepname": "3-Propose",
        "salesstagecode": 1,
        "salesstage": 2,  # Propose
        "budget": 2_200,
        "products": [
            {"productnumber": "DM-MG20-CASE", "quantity": 40},
        ],
    },
    {
        "name":         "Dunmore High School — yearbook cardstock (seed)",
        "description":  "Yearbook production paper bundle: cardstock covers and uncoated text pages for the 2026 Dunmore HS yearbook run.",
        "account_name": "Dunmore High School",
        "contact_name": None,
        "customerneed":      "100 lb cardstock covers and 60 lb text pages for 800-copy yearbook run.",
        "proposedsolution":  "Dunder Mifflin Yearbook Bundle: cardstock + uncoated text stock.",
        "currentsituation":  "Previous vendor discontinued education pricing programme.",
        "stepname": "3-Propose",
        "salesstagecode": 1,
        "salesstage": 2,  # Propose
        "budget": 1_200,
        "products": [
            {"productnumber": "DM-CS65-CASE", "quantity": 10},
            {"productnumber": "DM-TS60-REAM", "quantity": 20},
        ],
    },
    {
        "name":         "Poor Richard's Pub — bar menu & event flyer stock (seed)",
        "description":  "Heavy matte paper supply for laminated bar menus, events boards, and weekly specials flyers.",
        "account_name": "Poor Richard's Pub",
        "contact_name": None,
        "customerneed":      "Durable laminate-ready paper for weekly specials boards and flyers.",
        "proposedsolution":  "Dunder Mifflin Heavy Matte 90 lb + laminate pouches starter pack.",
        "currentsituation":  "Owner Roy Anderson wants to cut printing costs by 20%.",
        "stepname": "4-Close",
        "salesstagecode": 1,
        "salesstage": 3,  # Close
        "budget": 200,
        "products": [
            {"productnumber": "DM-HM90-REAM", "quantity": 8},
        ],
    },
    {
        "name":         "Michael Scott Paper Company — re-acquisition paper supply (seed)",
        "description":  "Full reinstatement of the Michael Scott Paper Company account following re-acquisition by Dunder Mifflin.",
        "account_name": "Michael Scott Paper Company",
        "contact_name": "Michael Scott",
        "customerneed":      "Resume full paper supply following re-acquisition by Dunder Mifflin.",
        "proposedsolution":  "Dunder Mifflin Standard Copy Paper 20 lb — immediate resumption of account.",
        "currentsituation":  "Michael Scott Paper Co. absorbed back; account needs to be reinstated.",
        "stepname": "4-Close",
        "salesstagecode": 1,
        "salesstage": 3,  # Close
        "budget": 1_200,
        "products": [
            {"productnumber": "DM-CP20-CASE", "quantity": 25},
        ],
    },
    {
        "name":         "Scranton City Hall — annual paper procurement (seed)",
        "description":  "Annual municipal paper supply contract covering all city departments and public offices.",
        "account_name": "Scranton City Hall",
        "contact_name": None,
        "customerneed":      "High-volume acid-free and medical-grade paper for city admin and public health offices.",
        "proposedsolution": "DM Medical Grade + Standard Copy Paper — bulk municipal contract with quarterly delivery.",
        "currentsituation": "Current city contract expiring; procurement office inviting tenders.",
        "stepname": "1-Qualify",
        "salesstagecode": 1,
        "salesstage": 0,  # Qualify
        "budget": 21_600,
        "products": [
            {"productnumber": "DM-MG20-CASE", "quantity": 200},
            {"productnumber": "DM-CP20-CASE", "quantity": 200},
            {"productnumber": "DM-CS65-CASE", "quantity":  20},
        ],
    },
    {
        "name":         "Geisinger Health System — regional paper contract (seed)",
        "description":  "Regional multi-site paper supply contract for Geisinger's hospital network across NEPA.",
        "account_name": "Geisinger Health System",
        "contact_name": None,
        "customerneed":      "HIPAA-compliant and premium paper for EHR, correspondence and cardiology print labs.",
        "proposedsolution": "DM Medical Grade + Premium 24 lb + Cardstock assortment — multi-site regional contract.",
        "currentsituation": "Vendor consolidation initiative; Geisinger reducing suppliers from 6 to 2.",
        "stepname": "3-Propose",
        "salesstagecode": 1,
        "salesstage": 2,  # Propose
        "budget": 21_900,
        "products": [
            {"productnumber": "DM-MG20-CASE", "quantity": 250},
            {"productnumber": "DM-CP24-CASE", "quantity": 100},
            {"productnumber": "DM-CS65-CASE", "quantity":  30},
        ],
    },
]


# ── Seeded accounts ───────────────────────────────────────────────────────────
# These accounts match the ``account_name`` values used in ``_SCENARIOS``.
# ``seed_accounts()`` will find-or-create each one at runtime.
_ACCOUNTS: list[dict] = [
    {
        "name":                     "Lackawanna County School District",
        "telephone1":               "+1-570-963-6800",
        "emailaddress1":            "procurement@lackawannaschools.org",
        "address1_line1":           "123 Education Way",
        "address1_city":            "Scranton",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18503",
        "address1_country":         "United States",
        "numberofemployees":        1200,
        "revenue":                  15000000.0,
        "description":              "Public school district covering 42 schools in Lackawanna County, Pennsylvania.",
        "websiteurl":               "https://www.lackawannaschools.org",
    },
    {
        "name":                     "Scranton Business Park",
        "telephone1":               "+1-570-555-0110",
        "emailaddress1":            "facilities@scrantonbp.com",
        "address1_line1":           "1200 Corporate Drive",
        "address1_city":            "Scranton",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18505",
        "address1_country":         "United States",
        "numberofemployees":        45,
        "revenue":                  3200000.0,
        "description":              "Commercial real-estate property management for a multi-tenant business park in Scranton.",
        "websiteurl":               "https://www.scrantonbp.com",
    },
    {
        "name":                     "Vance Refrigeration",
        "telephone1":               "+1-570-555-0101",
        "emailaddress1":            "bob.vance@vancerefrigeration.com",
        "address1_line1":           "1000 Industrial Blvd",
        "address1_city":            "Scranton",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18507",
        "address1_country":         "United States",
        "numberofemployees":        120,
        "revenue":                  8500000.0,
        "description":              "Commercial refrigeration manufacturer and installer serving northeast Pennsylvania.",
        "websiteurl":               "https://www.vancerefrigeration.com",
    },
    {
        "name":                     "Steamtown Mall",
        "telephone1":               "+1-570-344-6900",
        "emailaddress1":            "marketing@steamtownmall.com",
        "address1_line1":           "300 Lackawanna Ave",
        "address1_city":            "Scranton",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18503",
        "address1_country":         "United States",
        "numberofemployees":        220,
        "revenue":                  22000000.0,
        "description":              "Regional shopping mall in downtown Scranton with 90+ retail tenants.",
        "websiteurl":               "https://www.steamtownmall.com",
    },
    {
        "name":                     "Cooper & Greene Law Firm",
        "telephone1":               "+1-570-555-0200",
        "emailaddress1":            "info@coopergreenelaw.com",
        "address1_line1":           "500 Spruce Street",
        "address1_city":            "Scranton",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18503",
        "address1_country":         "United States",
        "numberofemployees":        38,
        "revenue":                  4700000.0,
        "description":              "Mid-size corporate and litigation law firm serving Lackawanna County businesses.",
        "websiteurl":               "https://www.coopergreenelaw.com",
    },
    {
        "name":                     "Dunder Mifflin",
        "telephone1":               "+1-570-555-0150",
        "emailaddress1":            "info@dundermifflin.com",
        "address1_line1":           "1725 Slough Avenue",
        "address1_city":            "Scranton",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18503",
        "address1_country":         "United States",
        "numberofemployees":        900,
        "revenue":                  84000000.0,
        "description":              "Dunder Mifflin Inc. \u2014 Scranton branch. Paper and office supply wholesale distributor.",
        "websiteurl":               "https://www.dundermifflin.com",
    },
    {
        "name":                     "Northeastern Pennsylvania Hospital",
        "telephone1":               "+1-570-555-0300",
        "emailaddress1":            "procurement@nepahospital.org",
        "address1_line1":           "700 Quincy Avenue",
        "address1_city":            "Scranton",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18510",
        "address1_country":         "United States",
        "numberofemployees":        2100,
        "revenue":                  310000000.0,
        "description":              "Full-service regional medical centre and teaching hospital serving Northeast Pennsylvania.",
        "websiteurl":               "https://www.nepahospital.org",
    },
    {
        "name":                     "Dunmore High School",
        "telephone1":               "+1-570-343-2110",
        "emailaddress1":            "office@dunmoreschools.org",
        "address1_line1":           "300 W Warren St",
        "address1_city":            "Dunmore",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18512",
        "address1_country":         "United States",
        "numberofemployees":        180,
        "revenue":                  5200000.0,
        "description":              "Public secondary school in Dunmore Borough, Lackawanna County.",
        "websiteurl":               "https://www.dunmoreschools.org",
    },
    {
        "name":                     "Poor Richard's Pub",
        "telephone1":               "+1-570-555-0400",
        "emailaddress1":            "events@poorrichardspub.com",
        "address1_line1":           "78 Main Ave",
        "address1_city":            "Scranton",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18504",
        "address1_country":         "United States",
        "numberofemployees":        22,
        "revenue":                  680000.0,
        "description":              "Neighbourhood pub and event venue in central Scranton.",
        "websiteurl":               "https://www.poorrichardspub.com",
    },
    {
        "name":                     "Michael Scott Paper Company",
        "telephone1":               "+1-570-555-0199",
        "emailaddress1":            "michael@michaelscottpaperco.com",
        "address1_line1":           "1725 Slough Avenue, Suite 200",
        "address1_city":            "Scranton",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18503",
        "address1_country":         "United States",
        "numberofemployees":        3,
        "revenue":                  120000.0,
        "description":              "Boutique paper reseller founded by Michael Scott; re-acquired by Dunder Mifflin.",
        "websiteurl":               "https://www.michaelscottpaperco.com",
    },
    {
        "name":                     "Scranton City Hall",
        "telephone1":               "+1-570-348-4000",
        "emailaddress1":            "procurement@scrantoncity.gov",
        "address1_line1":           "340 N Washington Ave",
        "address1_city":            "Scranton",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "18503",
        "address1_country":         "United States",
        "numberofemployees":        650,
        "revenue":                  85000000.0,
        "description":              "City of Scranton municipal government — procurement department.",
        "websiteurl":               "https://www.scrantonpa.gov",
    },
    {
        "name":                     "Geisinger Health System",
        "telephone1":               "+1-570-271-6211",
        "emailaddress1":            "supply.chain@geisinger.edu",
        "address1_line1":           "100 N Academy Ave",
        "address1_city":            "Danville",
        "address1_stateorprovince": "PA",
        "address1_postalcode":      "17822",
        "address1_country":         "United States",
        "numberofemployees":        24000,
        "revenue":                  6800000000.0,
        "description":              "Geisinger Health System — integrated health system serving northeast and central Pennsylvania.",
        "websiteurl":               "https://www.geisinger.org",
    },
]


# ── Seeded contacts ───────────────────────────────────────────────────────────
# These contacts match the ``contact_name`` values used in ``_SCENARIOS``.
# ``account_name`` is a lookup hint *only* — it is excluded from the Dataverse
# payload and replaced by a ``parentcustomerid@odata.bind`` navigation property.
_CONTACTS: list[dict] = [
    {
        "firstname":     "Bob",
        "lastname":      "Vance",
        "emailaddress1": "bob.vance@vancerefrigeration.com",
        "telephone1":    "+1-570-555-0101",
        "jobtitle":      "CEO",
        "description":   "Owner and CEO of Vance Refrigeration. Key decision-maker for all vendor contracts.",
        "account_name":  "Vance Refrigeration",
    },
    {
        "firstname":     "Michael",
        "lastname":      "Scott",
        "emailaddress1": "michael.scott@michaelscottpaperco.com",
        "telephone1":    "+1-570-555-0199",
        "jobtitle":      "President",
        "description":   "Founder and president of Michael Scott Paper Company, former Dunder Mifflin regional manager.",
        "account_name":  "Michael Scott Paper Company",
    },
]


# ── Seeded price list ─────────────────────────────────────────────────────────
# A single Dunder Mifflin price list is seeded and shared by every opportunity
# and every product.  ``seed_price_list()`` will find-or-create it at runtime.
_PRICE_LIST_NAME = "Dunder Mifflin — Standard Price List"

_PRICE_LIST_ITEMS: list[dict] = [
    {"productnumber": "DM-CP20-CASE",  "amount":  45.99},
    {"productnumber": "DM-CP24-CASE",  "amount":  58.99},
    {"productnumber": "DM-CB28-REAM",  "amount":  12.99},
    {"productnumber": "DM-ENV10-BOX",  "amount":   8.49},
    {"productnumber": "DM-LP-PACK",    "amount":   6.99},
    {"productnumber": "DM-CS65-CASE",  "amount":  89.99},
    {"productnumber": "DM-CS80G-REAM", "amount":  18.99},
    {"productnumber": "DM-TS60-REAM",  "amount":  14.99},
    {"productnumber": "DM-HM90-REAM",  "amount":  22.99},
    {"productnumber": "DM-MG20-CASE",  "amount":  52.99},
]


# ══════════════════════════════════════════════════════════════════════════════
#  Core helpers
# ══════════════════════════════════════════════════════════════════════════════

def _build_opportunity(
    scenario: dict,
    owner_id: str,
    budget: int,
    currency_id: str,
    price_list_id: str,
    account_id: Optional[str],
    contact_id: Optional[str],
) -> dict:
    """
    Return a dict of Opportunity field values ready for ``client.records.create``.

    All lookup bindings (currency, price list, account, contact) are passed in
    as resolved GUIDs so no module-level constants are needed.  Optional bindings
    (account, contact) are omitted when ``None``.  ``price_list_id`` is always
    supplied — it is the same price list used to seed the product catalogue.
    """
    payload: dict = {
        # ── Identity / ownership ──────────────────────────────────────────────
        "name":               scenario["name"],
        "ownerid@odata.bind": f"/systemusers({owner_id})",

        # ── Financials ────────────────────────────────────────────────────────
        "budgetamount":             float(budget),
        "estimatedvalue":           float(budget),
        "estimatedclosedate":       {0: "2026-09-30", 1: "2026-07-31", 2: "2026-06-30", 3: "2026-04-30"}.get(scenario["salesstage"], "2026-06-30"),
        "closeprobability":         50,
        "isrevenuesystemcalculated": True,
        "skippricecalculation":     0,
        "exchangerate":             1,
        "pricingerrorcode":         0,

        # ── Currency ──────────────────────────────────────────────────────────
        "transactioncurrencyid@odata.bind": f"/transactioncurrencies({currency_id})",

        # ── Status: Open / In Progress ────────────────────────────────────────
        "statecode":  0,   # 0 = Open
        "statuscode": 1,   # 1 = In Progress

        # ── Sales process ─────────────────────────────────────────────────────
        "salesstagecode":         scenario["salesstagecode"],
        "salesstage":             scenario["salesstage"],
        "stepname":               scenario["stepname"],
        "opportunityratingcode":  1,   # 1 = Hot
        "purchaseprocess":        1,   # 1 = Individual
        "prioritycode":           1,   # 1 = Default
        "msdyn_forecastcategory": 100000005,

        # ── Qualification flags ────────────────────────────────────────────────
        "identifypursuitteam":      False,
        "identifycustomercontacts": False,
        "identifycompetitors":      False,
        "decisionmaker":            False,
        "evaluatefit":              False,
        "presentproposal":          False,
        "captureproposalfeedback":  False,
        "developproposal":          False,
        "completeinternalreview":   False,
        "resolvefeedback":          False,
        "completefinalproposal":    False,
        "presentfinalproposal":     False,
        "sendthankyounote":         False,
        "filedebrief":              False,
        "confirminterest":          False,
        "pursuitdecision":          False,

        # ── Narrative fields ──────────────────────────────────────────────────
        "description":      scenario.get("description", ""),
        "customerneed":     scenario["customerneed"],
        "proposedsolution": scenario["proposedsolution"],
        "currentsituation": scenario["currentsituation"],

        # ── Misc ──────────────────────────────────────────────────────────────
        "msdyn_gdproptout":         False,
        "participatesinworkflow":   False,
        "importsequencenumber":     1,
        "timezoneruleversionnumber": 4,
    }
    payload["pricelevelid@odata.bind"] = f"/pricelevels({price_list_id})"
    if account_id:
        payload["parentaccountid@odata.bind"] = f"/accounts({account_id})"
    if contact_id:
        payload["parentcontactid@odata.bind"] = f"/contacts({contact_id})"
    return payload


def seed_price_list(
    client: DataverseClient,
    base_url: str,
    hdrs: dict,
    currency_id: str,
) -> str:
    """
    Find-or-create the Dunder Mifflin standard price list and populate it with
    a ``productpricelevel`` entry for every product in ``_PRICE_LIST_ITEMS``.

    Uses the same ``currency_id`` as the seeded opportunities so that products
    and opportunities share the same price list without currency conflicts.

    :returns: ``pricelevelid`` of the seeded price list.
    """
    print("\n  Seeding Price List...")
    safe_name = _PRICE_LIST_NAME.replace("'", "''")

    # ── Find-or-create the price list header ──────────────────────────────────
    price_list_id, _ = _find_or_create(
        label=_PRICE_LIST_NAME,
        base_url=base_url, headers=hdrs,
        entity_set="pricelevels",
        id_field="pricelevelid",
        filter_=f"name eq '{safe_name}'",
        create_fn=lambda: client.records.create(  # type: ignore[return-value]
            "pricelevel",
            {
                "name": _PRICE_LIST_NAME,
                "transactioncurrencyid@odata.bind": f"/transactioncurrencies({currency_id})",
            },
        ),
    )

    # ── Upsert price list items ────────────────────────────────────────────────
    print(f"    Populating price list items...")
    for item in _PRICE_LIST_ITEMS:
        pn   = item["productnumber"]
        prod = _get_first(
            base_url, hdrs, "products",
            select="productid,_defaultuomid_value,_defaultuomscheduleid_value",
            filter_=f"productnumber eq '{pn}' and statecode eq 0",
        )
        if not prod:
            print(f"       [SKIP] product {pn} not found or not Active — item omitted.")
            continue

        product_id   = prod["productid"]
        uom_id       = prod["_defaultuomid_value"]
        uom_sched_id = prod["_defaultuomscheduleid_value"]

        # Idempotency: skip if a price list item for this product already exists
        existing = _get_first(
            base_url, hdrs, "productpricelevels",
            select="productpricelevelid",
            filter_=f"_pricelevelid_value eq {price_list_id} and _productid_value eq {product_id}",
        )
        if existing:
            print(f"       [SKIP] {pn} (price list item already exists)")
            continue

        client.records.create(
            "productpricelevel",
            {
                "pricelevelid@odata.bind":          f"/pricelevels({price_list_id})",
                "productid@odata.bind":             f"/products({product_id})",
                "uomid@odata.bind":                 f"/uoms({uom_id})",
                "uomscheduleid@odata.bind":         f"/uomschedules({uom_sched_id})",
                "transactioncurrencyid@odata.bind": f"/transactioncurrencies({currency_id})",
                "amount":                           item["amount"],
                "pricingmethodcode":                1,   # 1 = Currency Amount
                "quantitysellingcode":              1,   # 1 = Whole units
            },
        )
        print(f"       [NEW]  {pn} @ £{item['amount']:.2f}")

    return price_list_id


def seed_accounts(
    client: DataverseClient,
    base_url: str,
    hdrs: dict,
) -> dict[str, str]:
    """
    Idempotently seed all ``_ACCOUNTS`` records.

    :returns: ``{account_name: accountid}`` for every seeded account.
    """
    print("\n  Seeding Accounts...")
    account_ids: dict[str, str] = {}
    for acct in _ACCOUNTS:
        safe_name = acct["name"].replace("'", "''")
        acct_id, _ = _find_or_create(
            label=acct["name"],
            base_url=base_url, headers=hdrs,
            entity_set="accounts",
            id_field="accountid",
            filter_=f"name eq '{safe_name}'",
            create_fn=lambda a=acct: client.records.create(  # type: ignore[return-value]
                "account", dict(a),
            ),
        )
        account_ids[acct["name"]] = acct_id
    return account_ids


def seed_contacts(
    client: DataverseClient,
    base_url: str,
    hdrs: dict,
    account_ids: dict[str, str],
) -> dict[str, str]:
    """
    Idempotently seed all ``_CONTACTS`` records and bind each to its parent account.

    ``account_name`` in each contact entry is a lookup hint only — it is excluded
    from the Dataverse payload and replaced by ``parentcustomerid@odata.bind``.

    :param account_ids: Mapping returned by :func:`seed_accounts`.
    :returns: ``{fullname: contactid}`` for every seeded contact.
    """
    print("\n  Seeding Contacts...")
    contact_ids: dict[str, str] = {}
    for contact in _CONTACTS:
        fullname  = f"{contact['firstname']} {contact['lastname']}"
        safe_fn   = fullname.replace("'", "''")
        contact_id, _ = _find_or_create(
            label=fullname,
            base_url=base_url, headers=hdrs,
            entity_set="contacts",
            id_field="contactid",
            filter_=f"fullname eq '{safe_fn}'",
            create_fn=lambda c=contact, aids=account_ids: client.records.create(  # type: ignore[return-value]
                "contact",
                {
                    **{k: v for k, v in c.items() if k != "account_name"},
                    **(
                        {"parentcustomerid_account@odata.bind": f"/accounts({aids[c['account_name']]})"}
                        if c.get("account_name") and c["account_name"] in aids else {}
                    ),
                },
            ),
        )
        contact_ids[fullname] = contact_id
    return contact_ids


def _add_opportunity_products(
    client: DataverseClient,
    base_url: str,
    hdrs: dict,
    opp_id: str,
    products: list[dict],
) -> list[str]:
    """
    Create ``opportunityproduct`` line items for one opportunity.

    Each ``products`` entry must have ``productnumber`` and ``quantity``.
    Products are looked up by ``productnumber`` among Active (statecode=1)
    published products.  Silently skips any product not found.

    :returns: List of created ``opportunityproductid`` GUIDs.
    """
    created: list[str] = []
    for item in products:
        pn   = item["productnumber"]
        prod = _get_first(
            base_url, hdrs, "products",
            select="productid,_defaultuomid_value",
            filter_=f"productnumber eq '{pn}' and statecode eq 0",
        )
        if not prod:
            print(f"       [SKIP] product {pn} not found or not Active \u2014 line omitted.")
            continue
        product_id = prod["productid"]
        uom_id     = prod["_defaultuomid_value"]
        try:
            line_id: str = client.records.create(  # type: ignore[assignment]
                "opportunityproduct",
                {
                    "opportunityid@odata.bind": f"/opportunities({opp_id})",
                    "productid@odata.bind":     f"/products({product_id})",
                    "uomid@odata.bind":         f"/uoms({uom_id})",
                    "quantity":                 float(item["quantity"]),
                    "ispriceoverridden":        False,
                },
            )
            created.append(line_id)
            print(f"       [NEW]  {pn} \u00d7 {item['quantity']}")
        except Exception as exc:
            print(f"       [WARN] {pn}: {exc}")
    return created


def seed_opportunities(client: DataverseClient, count: int = 12) -> list[str]:
    """
    Seed accounts, contacts and opportunities — all idempotent.

    Execution order:
      1. Seed ``_ACCOUNTS`` (find-or-create by name)
      2. Seed ``_CONTACTS`` (find-or-create by fullname, bound to parent account)
      3. Create ``count`` Opportunity records
      4. Create ``opportunityproduct`` line items for each opportunity

    All lookups are resolved from the API at runtime using values declared in
    each scenario and in the ``_ACCOUNTS`` / ``_CONTACTS`` catalogues.

    :param client: An authenticated :class:`~PowerPlatform.Dataverse.client.DataverseClient`.
    :param count: Number of opportunities to create (default 10, max 10).
    :returns: List of created ``opportunityid`` GUIDs.
    """
    base_url, hdrs = _http_headers(client)

    # ── Owner (WhoAmI) ────────────────────────────────────────────────────────
    who_resp = _req.get(f"{base_url}/api/data/v9.2/WhoAmI()", headers=hdrs)
    who_resp.raise_for_status()
    owner_id: str = who_resp.json()["UserId"]
    print(f"  Owner : {owner_id}")

    # ── Currency: prefer GBP, fall back to first available ────────────────────
    currency = (
        _get_first(base_url, hdrs, "transactioncurrencies",
                   "transactioncurrencyid,isocurrencycode",
                   "isocurrencycode eq 'GBP'")
        or _get_first(base_url, hdrs, "transactioncurrencies",
                      "transactioncurrencyid,isocurrencycode")
    )
    if not currency:
        raise RuntimeError("No transaction currency found in the environment.")
    currency_id: str = currency["transactioncurrencyid"]
    print(f"  Currency : {currency['isocurrencycode']} ({currency_id})")

    # ── Price list (seeded, shared with products) ─────────────────────────────
    price_list_id: str = seed_price_list(client, base_url, hdrs, currency_id)

    # ── Seed accounts & contacts ───────────────────────────────────────────────
    account_ids = seed_accounts(client, base_url, hdrs)
    contact_ids = seed_contacts(client, base_url, hdrs, account_ids)

    # ── Build opportunity payloads ─────────────────────────────────────────────
    scenarios = _SCENARIOS[:count]
    payloads: list[dict] = []

    for scenario in scenarios:
        account_id: Optional[str] = account_ids.get(scenario.get("account_name") or "")
        contact_id: Optional[str] = (
            contact_ids.get(scenario["contact_name"])
            if scenario.get("contact_name") else None
        )
        payloads.append(
            _build_opportunity(
                scenario, owner_id,
                budget=scenario["budget"],
                currency_id=currency_id,
                price_list_id=price_list_id,
                account_id=account_id,
                contact_id=contact_id,
            )
        )

    # ── Create opportunities ───────────────────────────────────────────────────
    print(f"\n  Creating {len(payloads)} opportunities...")
    created_ids: list[str] = client.records.create("opportunity", payloads)  # type: ignore[assignment]

    # ── Add opportunity product line items ─────────────────────────────────────
    print("\n  Adding opportunity products...")
    for opp_id, scenario in zip(created_ids, scenarios):
        if scenario.get("products"):
            print(f"    {scenario['name'][:65]}...")
            _add_opportunity_products(client, base_url, hdrs, opp_id, scenario["products"])

    return created_ids


# ══════════════════════════════════════════════════════════════════════════════
#  Standalone entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("Opportunity Seed Script  (accounts \u2022 contacts \u2022 opportunities \u2022 products)")
    print("=" * 70)

    tenant_id     = os.getenv("AZURE_TENANT_ID")
    client_id     = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    dataverse_url = os.getenv("DATAVERSE_URL")

    if not all([tenant_id, client_id, client_secret, dataverse_url]):
        raise EnvironmentError(
            "Missing required environment variables. "
            "Add AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, "
            "and DATAVERSE_URL to your .env file."
        )

    assert tenant_id and client_id and client_secret and dataverse_url

    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )

    with DataverseClient(dataverse_url, credential) as client:
        print("\nSeeding accounts, contacts, opportunities and products...")
        ids = seed_opportunities(client, count=10)

    print(f"\n{len(ids)} opportunity record(s) created:\n")
    for i, opp_id in enumerate(ids, start=1):
        print(f"  {i:>2}. {opp_id}")

    print(
        "\nAll records are Open (statecode=0 / statuscode=1).\n"
        "Re-running is safe \u2014 accounts and contacts that already exist are skipped.\n"
        "To delete the opportunities, run:\n"
        "  client.records.delete('opportunity', ids, use_bulk_delete=True)\n"
    )


if __name__ == "__main__":
    main()
