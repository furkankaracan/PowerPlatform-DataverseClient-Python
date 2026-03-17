# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Sales Dashboard extension for the Dataverse SDK.

Provides:
  - ``AccountSalesDashboard``  — queries accounts whose total opportunity pipeline value
    meets a configurable threshold, then renders a 4-panel executive chart.
  - ``send_top_accounts_notification`` — posts a Dataverse in-app notification
    to the currently authenticated user summarising the top 5 accounts.

Optional dependencies (must be installed separately):
    pip install pandas matplotlib

References:
    Sales Order entity:
        https://learn.microsoft.com/en-us/dynamics365/developer/reference/entities/salesorder
    In-App Notifications:
        https://learn.microsoft.com/en-us/power-apps/developer/model-driven-apps/clientapi/send-in-app-notifications
"""

from __future__ import annotations

# Standard library
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

# requests is already a required SDK dependency
import requests

# pandas and matplotlib are optional — we import them lazily inside methods
# so the module can still be imported even if they are not installed.
try:
    import pandas as pd                # type: ignore[import]
    import matplotlib.pyplot as plt    # type: ignore[import]
    import matplotlib.gridspec as gridspec  # type: ignore[import]
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False
    pd = None           # type: ignore[assignment]  # always bound; None until installed
    plt = None          # type: ignore[assignment]
    gridspec = None     # type: ignore[assignment]

if TYPE_CHECKING:
    # Only used for type hints — not imported at runtime
    from pandas import DataFrame as PandasDataFrame  # type: ignore[import]
    from ..client import DataverseClient

__all__ = ["AccountSalesDashboard", "send_top_accounts_notification"]


# ══════════════════════════════════════════════════════════════════════════════
#  AccountSalesDashboard
# ══════════════════════════════════════════════════════════════════════════════

class AccountSalesDashboard:
    """
    C-Level dashboard for account sales performance.

    Fetches sales order data from Dataverse, aggregates it per account
    using pandas, and renders a multi-panel executive chart.

    :param client: An authenticated :class:`~PowerPlatform.Dataverse.client.DataverseClient`.
    :param min_amount: Minimum total order value (GBP) to include an account.
        Defaults to 1 000.

    Example::

        from PowerPlatform.Dataverse.extensions.sales_dashboard import AccountSalesDashboard

        dashboard = AccountSalesDashboard(client, min_amount=1_000)
        df = dashboard.fetch_accounts_with_orders()
        dashboard.create_dashboard(df)
    """

    def __init__(self, client: "DataverseClient", min_amount: float = 1_000) -> None:
        self._client = client
        self.min_amount = min_amount   # Threshold — callers may override for testing

    # ------------------------------------------------------------------
    # Public: fetch + aggregate
    # ------------------------------------------------------------------

    def fetch_accounts_with_orders(self) -> "PandasDataFrame":
        """
        Return a DataFrame of accounts whose total pipeline value >= ``min_amount``.

        Columns in the returned DataFrame:
            - ``account_id``   — Dataverse account GUID
            - ``total_amount`` — sum of ``estimatedvalue`` across all non-lost opportunities
            - ``order_count``  — number of opportunities linked to the account
            - ``account_name`` — human-readable name from the account table

        :raises ImportError: If ``pandas`` is not installed.
        :return: Aggregated DataFrame, sorted descending by ``total_amount``.
            Empty DataFrame when no qualifying accounts exist.
        :rtype: pd.DataFrame
        """
        _require_pandas()
        assert pd is not None  # narrows pd: pandas | None → pandas after _require_pandas()

        # ── Build aggregate FetchXML ──────────────────────────────────────────
        # Uses server-side GROUP BY + SUM: returns one row per account (not per
        # opportunity), so only M aggregated rows are transferred instead of N raw
        # opportunity rows — a major improvement when volumes are large.
        #
        # The inner join limits results to accounts that have at least one
        # non-lost opportunity.  The link-entity filter acts as WHERE (applied
        # before the SUM), not HAVING, which is the correct semantic here.
        fetch_xml = (
            '<fetch aggregate="true">'
            '<entity name="account">'
            '<attribute name="accountid" groupby="true" alias="account_id" />'
            '<attribute name="name" groupby="true" alias="account_name" />'
            '<link-entity name="opportunity" from="parentaccountid" to="accountid"'
            ' link-type="inner" alias="O">'
            '<attribute name="estimatedvalue" aggregate="sum" alias="total_amount" />'
            '<attribute name="opportunityid" aggregate="countcolumn" alias="order_count" />'
            '<filter>'
            '<condition attribute="statecode" operator="ne" value="2" />'
            '</filter>'
            '</link-entity>'
            '</entity>'
            '</fetch>'
        )

        # ── Execute via raw HTTP (SDK has no FetchXML support) ────────────────
        base_url = self._client._base_url
        scope = f"{base_url}/.default"
        token = self._client.auth._acquire_token(scope).access_token

        headers = {
            "Authorization":    f"Bearer {token}",
            "OData-MaxVersion": "4.0",
            "OData-Version":    "4.0",
            "Accept":           "application/json",
        }

        rows: List[Any] = []
        url: Optional[str] = f"{base_url}/api/data/v9.2/accounts"
        params: Optional[Dict] = {"fetchXml": fetch_xml}

        while url:
            resp = requests.get(url, headers=headers, params=params)
            resp.raise_for_status()
            body = resp.json()
            rows.extend(body.get("value", []))
            url = body.get("@odata.nextLink")  # None when last page
            params = None  # subsequent pages: URL already contains encoded params

        if not rows:
            return pd.DataFrame()

        # ── Build and filter DataFrame ────────────────────────────────────────
        df = pd.DataFrame(rows)
        df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0.0)
        df["order_count"] = (
            pd.to_numeric(df["order_count"], errors="coerce").fillna(0).astype(int)
        )
        df["account_name"] = df["account_name"].fillna("Unknown Account")

        return (
            df[df["total_amount"] >= self.min_amount]
            .copy()[["account_id", "account_name", "total_amount", "order_count"]]
            .sort_values("total_amount", ascending=False)
            .reset_index(drop=True)
        )

    # ------------------------------------------------------------------
    # Public: render charts
    # ------------------------------------------------------------------

    def create_dashboard(self, df: "PandasDataFrame", top_n: int = 10, show_interactive: bool = False) -> str:
        """
        Render a 4-panel C-Level dashboard and save it as a PNG file.

        Panels:
            - **Top-left**:     Horizontal bar — top N accounts by revenue
            - **Top-right**:    Pie chart — revenue share among top N
            - **Bottom-left**:  Scatter — order count vs revenue
            - **Bottom-right**: Donut — top-5 accounts vs rest of portfolio

        :param df: DataFrame returned by :meth:`fetch_accounts_with_orders`.
        :param top_n: Number of accounts to show in bar and pie charts.
        :param show_interactive: If ``True``, display the chart in an interactive
            matplotlib window after saving. Blocks until the window is closed.
        :raises ImportError: If ``matplotlib`` is not installed.
        :return: Path of the saved PNG file.
        :rtype: str
        """
        _require_pandas()
        assert pd is not None and plt is not None and gridspec is not None

        if df.empty:
            raise ValueError("DataFrame is empty — nothing to chart.")

        df_top = df.head(top_n).copy()

        def _fmt_thousands(v: float) -> str:
            """Helper: '£1.2K' string from a float GBP value."""
            return f"£{v / 1_000:.1f}K"

        # ── Figure layout ─────────────────────────────────────────────────────
        fig = plt.figure(figsize=(20, 14))
        fig.suptitle(
            f"C-Level Revenue Dashboard  —  Accounts with Orders ≥ £1K\n"
            f"Generated {datetime.now():%Y-%m-%d %H:%M}",
            fontsize=15, fontweight="bold", y=0.98,
        )
        gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

        # ── Panel 1: Horizontal bar ────────────────────────────────────────────
        ax1 = fig.add_subplot(gs[0, 0])
        bars = ax1.barh(
            df_top["account_name"][::-1],
            df_top["total_amount"][::-1] / 1_000,
            color="steelblue", edgecolor="white",
        )
        ax1.set_xlabel("Total Revenue (£K)")
        ax1.set_title(f"Top {top_n} Accounts by Revenue", fontweight="bold")
        for bar in bars:
            ax1.text(
                bar.get_width() + 0.05,
                bar.get_y() + bar.get_height() / 2,
                f"£{bar.get_width():.1f}K",
                va="center", fontsize=8,
            )

        # ── Panel 2: Pie ───────────────────────────────────────────────────────
        ax2 = fig.add_subplot(gs[0, 1])
        pie_labels = [
            (n[:20] + "…") if len(n) > 20 else n
            for n in df_top["account_name"]
        ]
        ax2.pie(
            df_top["total_amount"], labels=pie_labels,
            autopct="%1.1f%%", startangle=140, textprops={"fontsize": 8},
        )
        ax2.set_title(f"Revenue Share — Top {top_n}", fontweight="bold")

        # ── Panel 3: Scatter ───────────────────────────────────────────────────
        ax3 = fig.add_subplot(gs[1, 0])
        ax3.scatter(
            df_top["order_count"], df_top["total_amount"] / 1_000,
            s=100, c=range(len(df_top)), cmap="viridis", alpha=0.8,
        )
        for _, row in df_top.iterrows():
            ax3.annotate(
                row["account_name"][:15],
                (row["order_count"], row["total_amount"] / 1_000),
                textcoords="offset points", xytext=(6, 4), fontsize=7,
            )
        ax3.set_xlabel("Number of Opportunities")
        ax3.set_ylabel("Total Revenue (£K)")
        ax3.set_title("Order Volume vs Revenue", fontweight="bold")
        ax3.grid(True, linestyle="--", alpha=0.5)

        # ── Panel 4: Donut ─────────────────────────────────────────────────────
        ax4 = fig.add_subplot(gs[1, 1])
        top5_total = df.head(5)["total_amount"].sum()
        rest_total  = df["total_amount"].sum() - top5_total
        ax4.pie(
            [top5_total, rest_total],
            labels=[
                f"Top 5\n{_fmt_thousands(top5_total)}",
                f"Others\n{_fmt_thousands(rest_total)}",
            ],
            autopct="%1.1f%%", startangle=90,
            colors=["#2196F3", "#B0BEC5"],
            wedgeprops={"width": 0.5},
            textprops={"fontsize": 9},
        )
        ax4.set_title("Top 5 Accounts vs Portfolio", fontweight="bold")
        grand_total = df["total_amount"].sum()
        ax4.text(
            0, 0, f"Total\n{_fmt_thousands(grand_total)}",
            ha="center", va="center", fontsize=10, fontweight="bold",
        )

        output_path = "c_level_dashboard.png"
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        if show_interactive:
            plt.show()   # Opens an interactive window; blocks until user closes it
        plt.close(fig)
        return output_path




# ══════════════════════════════════════════════════════════════════════════════
#  send_top_accounts_notification
# ══════════════════════════════════════════════════════════════════════════════

def send_top_accounts_notification(
    client: "DataverseClient",
    df: "PandasDataFrame",
    top_n: int = 5,
    recipient_email: Optional[str] = None,
) -> None:
    """
    Send a Dataverse in-app notification summarising the top N accounts.

    The notification appears in the 🔔 bell inside model-driven apps.

    Steps:
        1. Call ``WhoAmI()`` to resolve the current user's system user GUID.
        2. Format the top ``top_n`` rows into a human-readable message.
        3. POST to the ``SendAppNotification`` unbound action.

    :param client: Authenticated :class:`~PowerPlatform.Dataverse.client.DataverseClient`.
    :param df: DataFrame from :meth:`AccountSalesDashboard.fetch_accounts_with_orders`.
    :param top_n: How many accounts to include in the notification body.
    :param recipient_email: If provided, sends the notification to the Dataverse
        user whose ``internalemailaddress`` matches this value.
        If omitted, sends to the currently authenticated user via ``WhoAmI()``.
    :raises requests.HTTPError: If any HTTP call fails.
    :raises ValueError: If ``df`` is empty or ``recipient_email`` does not match any user.

    Reference:
        https://learn.microsoft.com/en-us/power-apps/developer/model-driven-apps/clientapi/send-in-app-notifications
    """
    if df.empty:
        raise ValueError("DataFrame is empty — nothing to notify about.")

    base_url = client._base_url

    # ── 1. Acquire bearer token ───────────────────────────────────────────────
    scope = f"{base_url}/.default"
    token = client.auth._acquire_token(scope).access_token

    headers = {
        "Authorization":    f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version":    "4.0",
        "Accept":           "application/json",
        "Content-Type":     "application/json; charset=utf-8",
    }

    # ── 2. Identify the recipient user ────────────────────────────────────────
    if recipient_email:
        safe_email = recipient_email.replace("'", "''")  # OData single-quote escape
        email_resp = requests.get(
            f"{base_url}/api/data/v9.2/systemusers",
            headers=headers,
            params={
                "$filter": f"internalemailaddress eq '{safe_email}'",
                "$select": "systemuserid",
            },
        )
        email_resp.raise_for_status()
        users = email_resp.json().get("value", [])
        if not users:
            raise ValueError(f"No system user found with email: {recipient_email}")
        user_id: str = users[0]["systemuserid"]
    else:
        who_resp = requests.get(f"{base_url}/api/data/v9.2/WhoAmI()", headers=headers)
        who_resp.raise_for_status()
        user_id = who_resp.json()["UserId"]

    # ── 3. Build notification body ────────────────────────────────────────────
    top_rows = df.head(top_n)
    lines = [f"Top {top_n} Accounts by Order Revenue:\n"]
    for rank, (_, row) in enumerate(top_rows.iterrows(), start=1):
        lines.append(
            f"  {rank}. {row['account_name']}: "
            f"${row['total_amount']:,.0f} "
            f"({int(row['order_count'])} orders)"
        )
    body = "\n".join(lines)

    # ── 4. POST SendAppNotification ───────────────────────────────────────────
    payload = {
        "Title":     "C-Level Dashboard — Top Accounts",
        "Body":      body,
        "Recipient": f"/systemusers({user_id})",  # OData entity-reference format
        "IconType":  100000000,   # 100000000 = Info (blue "i")
        "ToastType": 200000000,   # 200000000 = Timed (auto-dismiss)
    }
    notif_resp = requests.post(
        f"{base_url}/api/data/v9.2/SendAppNotification",
        headers=headers,
        json=payload,
    )
    notif_resp.raise_for_status()


# ══════════════════════════════════════════════════════════════════════════════
#  Module-level helpers
# ══════════════════════════════════════════════════════════════════════════════

def _require_pandas() -> None:
    """Raise a clear ImportError if pandas/matplotlib are not installed."""
    if not _PANDAS_AVAILABLE:
        raise ImportError(
            "pandas and matplotlib are required for sales_dashboard. "
            "Install them with:  pip install pandas matplotlib"
        )
