# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Seed Products — Dunder Mifflin Paper Catalog
=============================================

Creates the full Dunder Mifflin product catalog in Dataverse:

  1 Unit Group  ─  "Dunder Mifflin Paper Units"
  3 Units       ─  Ream (base, auto-created), Case (×10 reams), Pallet (×400 reams)
  2 Families    ─  "Paper — Standard", "Paper — Specialty Stock"
 10 Products    ─  5 per family, with costs and descriptions
 10 Price Items ─  one per product, linked to the seeded price list

Mock data mapping to the 8 requested fields
--------------------------------------------
  uomschedule      entity   : "Dunder Mifflin Paper Units"
  uom              entity   : Ream (base) / Case / Pallet
  parentproductid  entity   : one of the two Product Family records above
  currentcost      attribute: Dunder Mifflin sourcing cost in GBP
  standardcost     attribute: budgeted cost (~8% above current cost)
  price            attribute: list price on the price level item (~55% gross margin)
  quantitydecimal  attribute: 0 — paper is always sold in whole units
  subjectid        attribute: first Subject found in the environment (optional)

Creation dependency order
-------------------------
  uomschedule → uom (base auto-created) → uom (Case, Pallet)
  → product (Family) → product (leaf) → productpricelevel
  → PublishProductHierarchy (per family)

Usage
-----
  python examples/advanced/seed_products.py

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
#  Product catalog definition
# ══════════════════════════════════════════════════════════════════════════════
#
# Pricing rationale (GBP, typical paper distributor margins):
#   currentcost  ≈ actual sourcing / manufacturing cost
#   standardcost ≈ currentcost × 1.08   (8% budget contingency)
#   listprice    ≈ currentcost × 1.55   (~55% gross margin)
#
# quantitydecimal = 0 for all products — paper is sold in whole units only.

_FAMILIES: dict[str, dict] = {
    "standard": {
        "name":          "Paper — Standard",
        "productnumber": "DM-FAM-STD",
        "description":   "Everyday copy and writing paper lines for general office use.",
    },
    "specialty": {
        "name":          "Paper — Specialty Stock",
        "productnumber": "DM-FAM-SPEC",
        "description":   "Specialist print stocks: gloss, matte, cardstock, and compliance paper.",
    },
}

_PRODUCTS = [
    # ── Paper — Standard ──────────────────────────────────────────────────────
    {
        "productnumber": "DM-CP20-CASE",
        "name":          "Copy Paper 20 lb — Case (10 reams)",
        "description":   (
            "Standard 20 lb multipurpose copy paper. 500 sheets per ream, "
            "10 reams per case. Acid-free; works with all laser and inkjet printers."
        ),
        "family":        "standard",
        "uom":           "case",
        # quantitydecimal: 0 — sold in whole cases
        "currentcost":   24.00,
        "standardcost":  26.00,
        "listprice":     38.00,
        "quantitydecimal": 0,
    },
    {
        "productnumber": "DM-CP24-CASE",
        "name":          "Premium Copy Paper 24 lb Bright White — Case (10 reams)",
        "description":   (
            "Bright white 24 lb premium paper. Higher brightness (98 ISO) reduces "
            "paper-jam rate vs standard 20 lb. Ideal for colour printing."
        ),
        "family":        "standard",
        "uom":           "case",
        "currentcost":   32.00,
        "standardcost":  34.50,
        "listprice":     52.00,
        "quantitydecimal": 0,
    },
    {
        "productnumber": "DM-CB28-REAM",
        "name":          "Cotton Bond Letterhead Paper 28 lb — Ream",
        "description":   (
            "25% cotton bond, 28 lb. Custom watermark available on order. "
            "Preferred by law firms and executives for formal correspondence."
        ),
        "family":        "standard",
        "uom":           "ream",
        # quantitydecimal: 0 — sold by the ream (500 sheets)
        "currentcost":   8.50,
        "standardcost":  9.20,
        "listprice":     14.50,
        "quantitydecimal": 0,
    },
    {
        "productnumber": "DM-ENV10-BOX",
        "name":          "#10 Business Envelopes — Box of 500",
        "description":   (
            "White #10 window envelopes. 24 lb. Gummed seal. "
            "500 envelopes per box. Compatible with standard DM letterhead."
        ),
        "family":        "standard",
        "uom":           "ream",   # 1 box priced as 1 unit on this price list
        "currentcost":   16.00,
        "standardcost":  17.00,
        "listprice":     28.00,
        "quantitydecimal": 0,
    },
    {
        "productnumber": "DM-LP-PACK",
        "name":          "Legal Pads 8.5×14 — Pack of 12",
        "description":   (
            "Canary yellow, wide-ruled, 50-sheet perforated legal pads. "
            "12 pads per pack. Staple-bound top."
        ),
        "family":        "standard",
        "uom":           "ream",   # 1 pack priced as 1 unit on this price list
        "currentcost":   11.00,
        "standardcost":  12.00,
        "listprice":     19.50,
        "quantitydecimal": 0,
    },
    # ── Paper — Specialty Stock ───────────────────────────────────────────────
    {
        "productnumber": "DM-CS65-CASE",
        "name":          "Cardstock 65 lb Assorted — Case (10 reams)",
        "description":   (
            "65 lb colour cardstock in assorted (10-colour) packs. "
            "10 reams per case. Suitable for covers, folders, and presentations."
        ),
        "family":        "specialty",
        "uom":           "case",
        "currentcost":   38.00,
        "standardcost":  41.00,
        "listprice":     62.00,
        "quantitydecimal": 0,
    },
    {
        "productnumber": "DM-CS80G-REAM",
        "name":          "Cover Stock 80 lb Glossy — Ream",
        "description":   (
            "80 lb gloss-coated cover stock. Vibrant colour reproduction. "
            "Ideal for brochures, promotional flyers, and restaurant menus."
        ),
        "family":        "specialty",
        "uom":           "ream",
        "currentcost":   12.00,
        "standardcost":  13.00,
        "listprice":     20.00,
        "quantitydecimal": 0,
    },
    {
        "productnumber": "DM-TS60-REAM",
        "name":          "Text Stock 60 lb Uncoated — Ream",
        "description":   (
            "60 lb uncoated offset text stock. Excellent ink absorption for "
            "offset printing. Widely used for yearbook interiors and booklets."
        ),
        "family":        "specialty",
        "uom":           "ream",
        "currentcost":   7.50,
        "standardcost":  8.10,
        "listprice":     12.50,
        "quantitydecimal": 0,
    },
    {
        "productnumber": "DM-HM90-REAM",
        "name":          "Heavy Matte Stock 90 lb — Ream",
        "description":   (
            "90 lb matte-coated heavy stock. Laminate-ready surface. "
            "Preferred by bars and restaurants for durable menus and event boards."
        ),
        "family":        "specialty",
        "uom":           "ream",
        "currentcost":   13.50,
        "standardcost":  14.60,
        "listprice":     22.00,
        "quantitydecimal": 0,
    },
    {
        "productnumber": "DM-MG20-CASE",
        "name":          "Medical Grade Paper 20 lb Acid-Free — Case (10 reams)",
        "description":   (
            "HIPAA-compliant laser paper. Chlorine-free, acid-free, and pH-neutral. "
            "Certified for EHR printouts and patient-facing documents."
        ),
        "family":        "specialty",
        "uom":           "case",
        "currentcost":   48.00,
        "standardcost":  52.00,
        "listprice":     78.00,
        "quantitydecimal": 0,
    },
]


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


# ══════════════════════════════════════════════════════════════════════════════
#  Core seeder
# ══════════════════════════════════════════════════════════════════════════════

def seed_products(client: DataverseClient) -> dict[str, list[str]]:
    """
    Create the full Dunder Mifflin product catalog — idempotent.

    Each step checks whether the record already exists (by its natural key)
    before creating it.  Re-running the script when all records are present
    prints ``[SKIP]`` for every record and makes no API writes.

    Returns a dict of all resolved GUIDs grouped by record type (whether newly
    created or already existing) so the caller can reference them:

    .. code-block:: python

        result = seed_products(client)
        # result["unit_group"]  → [uomschedule_id]
        # result["uoms"]        → [ream_id, case_id, pallet_id]
        # result["families"]    → [std_family_id, spec_family_id]
        # result["products"]    → [10 product ids]
        # result["price_items"] → [10 productpricelevel ids]

    :param client: An authenticated DataverseClient.
    :returns: Dict mapping record type → list of resolved GUIDs.
    """
    base_url, hdrs = _http_headers(client)

    # ── Step 0: Currency + Price List ─────────────────────────────────────────
    # Resolve currency at runtime (prefer GBP) so no fixed GUID is needed.
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

    _PRICE_LIST_NAME = "Dunder Mifflin \u2014 Standard Price List"
    _safe_pl_name    = _PRICE_LIST_NAME.replace("'", "''")
    price_list_id, _ = _find_or_create(
        label=_PRICE_LIST_NAME,
        base_url=base_url, headers=hdrs,
        entity_set="pricelevels",
        id_field="pricelevelid",
        filter_=f"name eq '{_safe_pl_name}'",
        create_fn=lambda: client.records.create(  # type: ignore[return-value]
            "pricelevel",
            {
                "name": _PRICE_LIST_NAME,
                "transactioncurrencyid@odata.bind": f"/transactioncurrencies({currency_id})",
            },
        ),
    )
    print(f"  Price List: {_PRICE_LIST_NAME} ({price_list_id})")

    # ── Step 1: Unit Group ────────────────────────────────────────────────────
    # uomschedule.baseuomname triggers Dataverse to auto-create the base UOM.
    # Natural key: name (unique constraint on uomschedule).
    print("  [1/7] Unit Group...")
    UG_NAME = "Dunder Mifflin Paper Units"
    ug_id, _ = _find_or_create(
        label=UG_NAME,
        base_url=base_url, headers=hdrs,
        entity_set="uomschedules",
        id_field="uomscheduleid",
        filter_=f"name eq '{UG_NAME}'",
        create_fn=lambda: client.records.create(   # type: ignore[return-value]
            "uomschedule",
            {"name": UG_NAME, "baseuomname": "Ream"},
        ),
    )

    # ── Step 2: Resolve base UOM (Ream) ───────────────────────────────────────
    # Dataverse auto-creates the base UOM when the Unit Group is created.
    # It exists whether we just created the UG or it was already there.
    print("  [2/7] Resolving base UOM (Ream)...")
    base_uom = _get_first(
        base_url, hdrs, "uoms",
        select="uomid,name",
        filter_=f"_uomscheduleid_value eq {ug_id} and quantity eq 1",
    )
    if not base_uom:
        raise RuntimeError(f"Base UOM not found for Unit Group {ug_id}")
    ream_id: str = base_uom["uomid"]
    print(f"     Ream (base): {ream_id}")

    # ── Step 3: Additional UOMs ───────────────────────────────────────────────
    # Natural key: name within the same unit group.
    print("  [3/7] Additional UOMs (Case, Pallet)...")
    case_id, _ = _find_or_create(
        label="Case (10 reams)",
        base_url=base_url, headers=hdrs,
        entity_set="uoms",
        id_field="uomid",
        filter_=f"name eq 'Case' and _uomscheduleid_value eq {ug_id}",
        create_fn=lambda: client.records.create(   # type: ignore[return-value]
            "uom",
            {
                "name": "Case", "quantity": 10,
                "uomscheduleid@odata.bind": f"/uomschedules({ug_id})",
                "baseuom@odata.bind":        f"/uoms({ream_id})",
            },
        ),
    )
    pallet_id, _ = _find_or_create(
        label="Pallet (400 reams)",
        base_url=base_url, headers=hdrs,
        entity_set="uoms",
        id_field="uomid",
        filter_=f"name eq 'Pallet' and _uomscheduleid_value eq {ug_id}",
        create_fn=lambda: client.records.create(   # type: ignore[return-value]
            "uom",
            {
                "name": "Pallet", "quantity": 400,
                "uomscheduleid@odata.bind": f"/uomschedules({ug_id})",
                "baseuom@odata.bind":        f"/uoms({ream_id})",
            },
        ),
    )
    uom_ids = {"ream": ream_id, "case": case_id, "pallet": pallet_id}

    # ── Step 4: Optional Subject lookup ──────────────────────────────────────
    print("  [4/7] Looking for a Subject record...")
    subj = _get_first(base_url, hdrs, "subjects", select="subjectid,title")
    subject_bind: Optional[str] = (
        f"/subjects({subj['subjectid']})" if subj else None
    )
    if subject_bind:
        print(f"     Using Subject: {subj['title']} ({subj['subjectid']})")   # type: ignore[index]
    else:
        print("     No subjects found — subjectid will be omitted")

    # ── Step 5: Product Families ──────────────────────────────────────────────
    # Natural key: productnumber (unique alternate key on the product entity).
    print("  [5/7] Product Families...")

    # Pre-flight: delete any wrong-type records that share a family productnumber
    # (e.g. productstructure=1 left over from an interrupted prior run).  If not
    # cleaned up, the create below would fail with a duplicate-key error even
    # though _find_or_create correctly skips them (they have the wrong type).
    for fam in _FAMILIES.values():
        bad = _get_first(
            base_url, hdrs, "products", "productid",
            f"productnumber eq '{fam['productnumber']}' and productstructure ne 2",
        )
        if bad:
            print(f"     [CLEANUP] Removing wrong-type record for {fam['productnumber']}...")
            client.records.delete("product", bad["productid"])

    family_ids: dict[str, str] = {}
    for key, fam in _FAMILIES.items():
        record_payload: dict = {
            "name":            fam["name"],
            "productnumber":   fam["productnumber"],
            "description":     fam["description"],
            "producttypecode": 3,        # 3 = Services (sales dimension, not family type)
            "productstructure": 2,       # 2 = Product Family
            "defaultuomscheduleid@odata.bind": f"/uomschedules({ug_id})",
            "defaultuomid@odata.bind":         f"/uoms({ream_id})",
            "pricelevelid@odata.bind":         f"/pricelevels({price_list_id})",
            "quantitydecimal": 0,
            "transactioncurrencyid@odata.bind": f"/transactioncurrencies({currency_id})",
        }
        if subject_bind:
            record_payload["subjectid@odata.bind"] = subject_bind

        fam_id, skipped = _find_or_create(
            label=fam["name"],
            base_url=base_url, headers=hdrs,
            entity_set="products",
            id_field="productid",
            filter_=f"productnumber eq '{fam['productnumber']}' and productstructure eq 2",
            create_fn=lambda rp=record_payload: client.records.create(  # type: ignore[return-value]
                "product", rp
            ),
        )
        family_ids[key] = fam_id

    # ── Step 6: Products ──────────────────────────────────────────────────────
    # Same pattern: upsert by productnumber, then resolve the ID.
    # currentcost / standardcost / quantitydecimal are set on first upsert;
    # on subsequent runs the record is skipped entirely.
    print("  [6/7] Products...")
    product_ids: list[str] = []
    product_uom_ids: list[str] = []

    for p in _PRODUCTS:
        uom_id = uom_ids[p["uom"]]
        record_payload = {
            "name":            p["name"],
            "productnumber":   p["productnumber"],
            "description":     p["description"],
            "producttypecode": 1,        # 1 = Sales Inventory (default product type)
            "productstructure": 1,       # 1 = Product (leaf, not family or bundle)
            "parentproductid@odata.bind":      f"/products({family_ids[p['family']]})",
            "defaultuomscheduleid@odata.bind": f"/uomschedules({ug_id})",
            "defaultuomid@odata.bind":          f"/uoms({uom_id})",
            "pricelevelid@odata.bind":          f"/pricelevels({price_list_id})",
            "currentcost":     p["currentcost"],
            "standardcost":    p["standardcost"],
            "quantitydecimal": p["quantitydecimal"],
            "validfromdate":   "2026-01-01",
            "validtodate":     "2028-12-31",
            "transactioncurrencyid@odata.bind": f"/transactioncurrencies({currency_id})",
        }
        if subject_bind:
            record_payload["subjectid@odata.bind"] = subject_bind

        prod_id, skipped = _find_or_create(
            label=p["productnumber"],
            base_url=base_url, headers=hdrs,
            entity_set="products",
            id_field="productid",
            filter_=f"productnumber eq '{p['productnumber']}'",
            create_fn=lambda rp=record_payload: client.records.create(  # type: ignore[return-value]
                "product", rp
            ),
        )
        product_ids.append(prod_id)
        product_uom_ids.append(uom_id)

    # ── Step 7: Price List Items ──────────────────────────────────────────────
    # productpricelevel has no registered alternate key, so we use
    # _find_or_create with a filter on pricelist + product.
    print("  [7/7] Price List Items...")
    price_item_ids: list[str] = []

    for prod_id, p, uom_id in zip(product_ids, _PRODUCTS, product_uom_ids):
        item_id, _ = _find_or_create(
            label=f"{p['productnumber']} @ £{p['listprice']:.2f}",
            base_url=base_url, headers=hdrs,
            entity_set="productpricelevels",
            id_field="productpricelevelid",
            filter_=(
                f"_pricelevelid_value eq {price_list_id} "
                f"and _productid_value eq {prod_id}"
            ),
            create_fn=lambda pid=prod_id, uid=uom_id, lp=p["listprice"], plid=price_list_id, cid=currency_id, ugid=ug_id: (
                client.records.create(   # type: ignore[return-value]
                    "productpricelevel",
                    {
                        "pricelevelid@odata.bind":          f"/pricelevels({plid})",
                        "productid@odata.bind":             f"/products({pid})",
                        "uomid@odata.bind":                 f"/uoms({uid})",
                        "uomscheduleid@odata.bind":         f"/uomschedules({ugid})",
                        "amount":              lp,
                        "pricingmethodcode":   1,   # 1 = Currency Amount
                        "quantitysellingcode": 1,   # 1 = Whole units
                        "transactioncurrencyid@odata.bind": f"/transactioncurrencies({cid})",
                    },
                )
            ),
        )
        price_item_ids.append(item_id)

    # ── Step 8: Publish product hierarchy ─────────────────────────────────────
    # PublishProductHierarchy is idempotent by nature — publishing an already-
    # active family is a no-op on the Dataverse side.
    print("  Publishing product hierarchies...")
    for fam_key, fam_id in family_ids.items():
        pub_resp = _req.post(
            f"{base_url}/api/data/v9.2/products({fam_id})/Microsoft.Dynamics.CRM.PublishProductHierarchy",
            headers=hdrs,
        )
        pub_resp.raise_for_status()
        print(f"     Published: {_FAMILIES[fam_key]['name']}")

    return {
        "unit_group":  [ug_id],
        "uoms":        [ream_id, case_id, pallet_id],
        "families":    list(family_ids.values()),
        "products":    product_ids,
        "price_items": price_item_ids,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  Standalone entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("Dunder Mifflin Product Catalog — Seed Script")
    print("=" * 55)

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

    print()
    with DataverseClient(dataverse_url, credential) as client:
        result = seed_products(client)

    total = sum(len(v) for v in result.values())
    print(f"\n{total} records created:")
    print(f"  Unit Group  : {result['unit_group'][0]}")
    print(f"  UOMs        : Ream={result['uoms'][0]}  Case={result['uoms'][1]}  Pallet={result['uoms'][2]}")
    print(f"  Families    : {', '.join(result['families'])}")
    print(f"  Products    : {len(result['products'])} records")
    print(f"  Price Items : {len(result['price_items'])} records")
    print(
        "\nTo delete everything (run in order):\n"
        "  client.records.delete('productpricelevel', result['price_items'], use_bulk_delete=True)\n"
        "  client.records.delete('product', result['products'] + result['families'], use_bulk_delete=True)\n"
        "  client.records.delete('uom', [result['uoms'][1], result['uoms'][2]], use_bulk_delete=True)\n"
        "  client.records.delete('uomschedule', result['unit_group'][0])\n"
        "  # Note: the base UOM (Ream) is deleted automatically with the Unit Group.\n"
    )


if __name__ == "__main__":
    main()
