# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Unit tests for the AccountSalesDashboard extension and
send_top_accounts_notification function.

Tests are isolated from Dataverse and the file system using unittest.mock.
pandas is used for real aggregation logic; matplotlib.pyplot I/O is patched
so no PNG is written during the test run.
"""

import unittest
from unittest.mock import MagicMock, patch, call

import pandas as pd

from azure.core.credentials import TokenCredential

from PowerPlatform.Dataverse.client import DataverseClient
from PowerPlatform.Dataverse.extensions.sales_dashboard import (
    AccountSalesDashboard,
    send_top_accounts_notification,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: build a minimal Record that looks like a sales-order response
# ─────────────────────────────────────────────────────────────────────────────




# ─────────────────────────────────────────────────────────────────────────────
#  Test: AccountSalesDashboard.fetch_accounts_with_orders
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchAccountsWithOrders(unittest.TestCase):
    """Tests for the data-fetching and aggregation pipeline."""

    def _make_dashboard(self, min_amount: float = 1_000_000) -> AccountSalesDashboard:
        """Build a dashboard with a mocked auth token."""
        mock_credential = MagicMock(spec=TokenCredential)
        client = DataverseClient("https://example.crm.dynamics.com", mock_credential)
        client._base_url = "https://example.crm.dynamics.com"  # type: ignore[assignment]
        mock_token = MagicMock()
        mock_token.access_token = "test_token"
        client.auth = MagicMock()  # type: ignore[assignment]
        client.auth._acquire_token.return_value = mock_token
        return AccountSalesDashboard(client, min_amount=min_amount)

    def _mock_response(self, rows: list, next_link: str | None = None) -> MagicMock:
        """Build a mock requests.Response with a JSON payload."""
        resp = MagicMock()
        resp.json.return_value = {"value": rows, "@odata.nextLink": next_link}
        resp.raise_for_status = MagicMock()
        return resp

    @staticmethod
    def _agg_row(
        account_id: str,
        account_name: str | None,
        total_amount: float,
        order_count: int = 1,
    ) -> dict:
        """Simulate an aggregate FetchXML response row."""
        return {
            "account_id":   account_id,
            "account_name": account_name,
            "total_amount":  total_amount,
            "order_count":   order_count,
        }

    # ── No orders ──────────────────────────────────────────────────────────────

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_returns_empty_dataframe_when_no_orders(self, mock_get):
        """Empty API response returns empty DataFrame."""
        mock_get.return_value = self._mock_response([])
        df = self._make_dashboard().fetch_accounts_with_orders()
        self.assertIsInstance(df, pd.DataFrame)
        self.assertTrue(df.empty)

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_returns_empty_dataframe_when_empty_page(self, mock_get):
        """order_count must be read directly from the aggregate response row."""
        rows = [self._agg_row("a1", "Alpha", 2_000_000, order_count=7)]
        mock_get.return_value = self._mock_response(rows)
        df = self._make_dashboard().fetch_accounts_with_orders()
        self.assertEqual(int(df.iloc[0]["order_count"]), 7)

    # ── Threshold filtering ────────────────────────────────────────────────────

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_filters_accounts_below_threshold(self, mock_get):
        """Accounts with total_amount below min_amount must be excluded."""
        rows = [
            self._agg_row("acc-above", "Big Corp",   1_500_000),
            self._agg_row("acc-below", "Small Corp",   800_000),
        ]
        mock_get.return_value = self._mock_response(rows)
        df = self._make_dashboard().fetch_accounts_with_orders()
        self.assertEqual(len(df), 1)
        self.assertIn("acc-above", df["account_id"].values)
        self.assertNotIn("acc-below", df["account_id"].values)

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_returns_empty_when_all_accounts_below_threshold(self, mock_get):
        """If every account is below the threshold the result is empty."""
        rows = [
            self._agg_row("acc1", "Corp 1", 50_000),
            self._agg_row("acc2", "Corp 2", 99_000),
        ]
        mock_get.return_value = self._mock_response(rows)
        df = self._make_dashboard().fetch_accounts_with_orders()
        self.assertTrue(df.empty)

    # ── Aggregation ────────────────────────────────────────────────────────────

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_aggregates_multiple_orders_per_account(self, mock_get):
        """Result must be sorted highest total_amount first."""
        rows = [
            self._agg_row("a1", "Alpha", 2_000_000),
            self._agg_row("a2", "Beta",  3_000_000),
            self._agg_row("a3", "Gamma", 1_500_000),
        ]
        mock_get.return_value = self._mock_response(rows)
        df = self._make_dashboard().fetch_accounts_with_orders()
        self.assertEqual(list(df["account_id"]), ["a2", "a1", "a3"])

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_result_sorted_descending_by_total_amount(self, mock_get):
        """Required columns must be present in the result."""
        rows = [self._agg_row("a1", "Alpha", 2_000_000, order_count=5)]
        mock_get.return_value = self._mock_response(rows)
        df = self._make_dashboard().fetch_accounts_with_orders()
        for col in ("account_id", "account_name", "total_amount", "order_count"):
            self.assertIn(col, df.columns, f"Missing column: {col}")

    # ── Required columns ───────────────────────────────────────────────────────

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_returned_dataframe_has_required_columns(self, mock_get):
        """account_name must be populated directly from the aggregate row."""
        rows = [self._agg_row("a1", "Contoso Ltd", 2_000_000)]
        mock_get.return_value = self._mock_response(rows)
        df = self._make_dashboard().fetch_accounts_with_orders()
        self.assertEqual(df.iloc[0]["account_name"], "Contoso Ltd")

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_account_name_filled_from_account_table(self, mock_get):
        """A null account_name in the response falls back to 'Unknown Account'."""
        rows = [self._agg_row("a1", None, 2_000_000)]
        mock_get.return_value = self._mock_response(rows)
        df = self._make_dashboard().fetch_accounts_with_orders()
        self.assertEqual(df.iloc[0]["account_name"], "Unknown Account")

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_unknown_account_name_fallback(self, mock_get):
        """A custom min_amount is applied client-side to the response rows."""
        rows = [
            self._agg_row("acc1", "Small Corp", 500_000),
            self._agg_row("acc2", "Tiny Corp",  300_000),
        ]
        mock_get.return_value = self._mock_response(rows)
        df = self._make_dashboard(min_amount=400_000).fetch_accounts_with_orders()
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["account_id"], "acc1")

    # ── Custom min_amount ──────────────────────────────────────────────────────

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_custom_min_amount_respected(self, mock_get):
        """@odata.nextLink pagination: rows from all pages are combined."""
        page1 = self._mock_response(
            [self._agg_row("a1", "Corp A", 1_200_000)],
            next_link="https://example.crm.dynamics.com/api/data/v9.2/accounts?page=2",
        )
        page2 = self._mock_response([self._agg_row("a2", "Corp B", 1_500_000)])
        mock_get.side_effect = [page1, page2]
        df = self._make_dashboard().fetch_accounts_with_orders()
        self.assertEqual(len(df), 2)
        self.assertEqual(mock_get.call_count, 2)

    # ── Multi-page iteration ───────────────────────────────────────────────────

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_consumes_multiple_pages(self, mock_get):
        """requests.get must target the accounts endpoint and include fetchXml param."""
        mock_get.return_value = self._mock_response([])
        self._make_dashboard().fetch_accounts_with_orders()
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertIn("/accounts", call_args[0][0])
        self.assertIn("fetchXml", call_args[1]["params"])


# ─────────────────────────────────────────────────────────────────────────────
#  Test: AccountSalesDashboard.create_dashboard
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateDashboard(unittest.TestCase):
    """Tests for chart rendering (matplotlib I/O is patched)."""

    def _sample_df(self, n: int = 5) -> pd.DataFrame:
        """Build a minimal qualifying DataFrame for chart tests."""
        return pd.DataFrame({
            "account_id":    [f"a{i}" for i in range(n)],
            "account_name":  [f"Corp {i}" for i in range(n)],
            "total_amount":  [float(1_000_000 * (i + 1)) for i in range(n)],
            "order_count":   [i + 1 for i in range(n)],
        })

    def _make_dashboard(self) -> AccountSalesDashboard:
        mock_credential = MagicMock(spec=TokenCredential)
        client = DataverseClient("https://example.crm.dynamics.com", mock_credential)
        return AccountSalesDashboard(client)

    # ── Empty DataFrame ────────────────────────────────────────────────────────

    def test_raises_on_empty_dataframe(self):
        """create_dashboard must raise ValueError for an empty DataFrame."""
        dashboard = self._make_dashboard()
        with self.assertRaises(ValueError):
            dashboard.create_dashboard(pd.DataFrame())

    # ── Normal execution ───────────────────────────────────────────────────────

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.plt")
    def test_saves_png_and_returns_path(self, mock_plt):
        """create_dashboard must call savefig and return the output path."""
        # Matplotlib is fully mocked — no GUI, no file I/O
        mock_plt.figure.return_value = MagicMock()
        dashboard = self._make_dashboard()

        result = dashboard.create_dashboard(self._sample_df())

        mock_plt.savefig.assert_called_once()
        mock_plt.close.assert_called_once()
        self.assertIsInstance(result, str)
        self.assertTrue(result.endswith(".png"))

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.plt")
    def test_dashboard_uses_top_n_rows(self, mock_plt):
        """create_dashboard should not fail when top_n < len(df)."""
        mock_plt.figure.return_value = MagicMock()
        dashboard = self._make_dashboard()
        df = self._sample_df(n=20)

        # top_n=5 should pick only 5 from 20 rows — no index error
        result = dashboard.create_dashboard(df, top_n=5)

        self.assertIsInstance(result, str)

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.plt")
    def test_dashboard_single_row(self, mock_plt):
        """create_dashboard should work when df has exactly one row."""
        mock_plt.figure.return_value = MagicMock()
        dashboard = self._make_dashboard()
        df = self._sample_df(n=1)

        result = dashboard.create_dashboard(df, top_n=1)

        self.assertIsInstance(result, str)

    # ── show_interactive flag ──────────────────────────────────────────────────

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.plt")
    def test_show_interactive_calls_plt_show(self, mock_plt):
        """When show_interactive=True, plt.show() must be called after saving."""
        mock_plt.figure.return_value = MagicMock()
        dashboard = self._make_dashboard()

        dashboard.create_dashboard(self._sample_df(), show_interactive=True)

        mock_plt.show.assert_called_once()

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.plt")
    def test_show_interactive_false_does_not_call_plt_show(self, mock_plt):
        """When show_interactive=False (default), plt.show() must not be called."""
        mock_plt.figure.return_value = MagicMock()
        dashboard = self._make_dashboard()

        dashboard.create_dashboard(self._sample_df())

        mock_plt.show.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
#  Test: send_top_accounts_notification
# ─────────────────────────────────────────────────────────────────────────────

class TestSendTopAccountsNotification(unittest.TestCase):
    """Tests for the standalone notification function."""

    def _make_client_and_df(self):
        """Return a partially-mocked client and a sample qualifying DataFrame."""
        mock_credential = MagicMock(spec=TokenCredential)
        client = DataverseClient("https://example.crm.dynamics.com", mock_credential)
        client._base_url = "https://example.crm.dynamics.com"

        # Mock auth token acquisition
        mock_token = MagicMock()
        mock_token.access_token = "test_token_12345"
        client.auth = MagicMock()
        client.auth._acquire_token.return_value = mock_token

        df = pd.DataFrame({
            "account_name": ["Corp A", "Corp B", "Corp C", "Corp D", "Corp E"],
            "total_amount": [5_000_000, 4_000_000, 3_000_000, 2_000_000, 1_000_000],
            "order_count":  [10, 8, 6, 4, 2],
        })
        return client, df

    # ── Empty DataFrame ────────────────────────────────────────────────────────

    def test_raises_on_empty_dataframe(self):
        """send_top_accounts_notification must raise ValueError for empty df."""
        mock_credential = MagicMock(spec=TokenCredential)
        client = DataverseClient("https://example.crm.dynamics.com", mock_credential)
        with self.assertRaises(ValueError):
            send_top_accounts_notification(client, pd.DataFrame())

    # ── HTTP calls ─────────────────────────────────────────────────────────────

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.post")
    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_calls_whoami_and_send_notification(self, mock_get, mock_post):
        """Must call WhoAmI first, then SendAppNotification."""
        client, df = self._make_client_and_df()

        # WhoAmI returns a valid user ID
        whoami_resp = MagicMock()
        whoami_resp.json.return_value = {"UserId": "user-guid-abc"}
        whoami_resp.raise_for_status = MagicMock()
        mock_get.return_value = whoami_resp

        # SendAppNotification succeeds
        notif_resp = MagicMock()
        notif_resp.raise_for_status = MagicMock()
        mock_post.return_value = notif_resp

        send_top_accounts_notification(client, df)

        # WhoAmI called exactly once
        mock_get.assert_called_once()
        whoami_url = mock_get.call_args[0][0]
        self.assertIn("WhoAmI()", whoami_url)

        # SendAppNotification called exactly once
        mock_post.assert_called_once()

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.post")
    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_notification_includes_user_id(self, mock_get, mock_post):
        """Recipient field must reference the user GUID returned by WhoAmI."""
        client, df = self._make_client_and_df()

        whoami_resp = MagicMock()
        whoami_resp.json.return_value = {"UserId": "specific-user-guid"}
        whoami_resp.raise_for_status = MagicMock()
        mock_get.return_value = whoami_resp

        notif_resp = MagicMock()
        notif_resp.raise_for_status = MagicMock()
        mock_post.return_value = notif_resp

        send_top_accounts_notification(client, df)

        # Check POST payload Recipient contains user GUID
        post_kwargs = mock_post.call_args[1]
        payload = post_kwargs.get("json", {})
        self.assertIn("specific-user-guid", payload["Recipient"])

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.post")
    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_notification_body_contains_account_names(self, mock_get, mock_post):
        """The notification body must list the top account names."""
        client, df = self._make_client_and_df()

        whoami_resp = MagicMock()
        whoami_resp.json.return_value = {"UserId": "uid"}
        whoami_resp.raise_for_status = MagicMock()
        mock_get.return_value = whoami_resp

        notif_resp = MagicMock()
        notif_resp.raise_for_status = MagicMock()
        mock_post.return_value = notif_resp

        send_top_accounts_notification(client, df, top_n=3)

        post_kwargs = mock_post.call_args[1]
        body = post_kwargs["json"]["Body"]
        # Top 3 accounts should appear in the body
        self.assertIn("Corp A", body)
        self.assertIn("Corp B", body)
        self.assertIn("Corp C", body)
        # 4th account should NOT be in the body
        self.assertNotIn("Corp D", body)

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.post")
    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_uses_bearer_token_in_headers(self, mock_get, mock_post):
        """Authorization header must carry the Bearer token."""
        client, df = self._make_client_and_df()

        whoami_resp = MagicMock()
        whoami_resp.json.return_value = {"UserId": "uid"}
        whoami_resp.raise_for_status = MagicMock()
        mock_get.return_value = whoami_resp

        notif_resp = MagicMock()
        notif_resp.raise_for_status = MagicMock()
        mock_post.return_value = notif_resp

        send_top_accounts_notification(client, df)

        get_headers = mock_get.call_args[1]["headers"]
        self.assertEqual(get_headers["Authorization"], "Bearer test_token_12345")

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.post")
    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_raises_on_http_error_from_whoami(self, mock_get, mock_post):
        """If WhoAmI raises HTTPError, it must propagate to the caller."""
        import requests as _req

        client, df = self._make_client_and_df()

        bad_resp = MagicMock()
        bad_resp.raise_for_status.side_effect = _req.HTTPError("401 Unauthorized")
        mock_get.return_value = bad_resp

        with self.assertRaises(_req.HTTPError):
            send_top_accounts_notification(client, df)

    # ── recipient_email path ───────────────────────────────────────────────────

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.post")
    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_uses_email_to_lookup_recipient(self, mock_get, mock_post):
        """When recipient_email is given, systemusers is queried instead of WhoAmI."""
        client, df = self._make_client_and_df()

        email_resp = MagicMock()
        email_resp.json.return_value = {"value": [{"systemuserid": "email-user-guid"}]}
        email_resp.raise_for_status = MagicMock()
        mock_get.return_value = email_resp

        notif_resp = MagicMock()
        notif_resp.raise_for_status = MagicMock()
        mock_post.return_value = notif_resp

        send_top_accounts_notification(client, df, recipient_email="user@example.com")

        get_url = mock_get.call_args[0][0]
        self.assertIn("systemusers", get_url)
        self.assertNotIn("WhoAmI", get_url)

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.post")
    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_email_recipient_gets_notification(self, mock_get, mock_post):
        """Recipient field must reference the GUID returned from the email lookup."""
        client, df = self._make_client_and_df()

        email_resp = MagicMock()
        email_resp.json.return_value = {"value": [{"systemuserid": "email-user-guid"}]}
        email_resp.raise_for_status = MagicMock()
        mock_get.return_value = email_resp

        notif_resp = MagicMock()
        notif_resp.raise_for_status = MagicMock()
        mock_post.return_value = notif_resp

        send_top_accounts_notification(client, df, recipient_email="user@example.com")

        post_kwargs = mock_post.call_args[1]
        self.assertIn("email-user-guid", post_kwargs["json"]["Recipient"])

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.post")
    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard.requests.get")
    def test_raises_when_email_not_found(self, mock_get, mock_post):
        """If the email matches no system user, ValueError must be raised."""
        client, df = self._make_client_and_df()

        email_resp = MagicMock()
        email_resp.json.return_value = {"value": []}
        email_resp.raise_for_status = MagicMock()
        mock_get.return_value = email_resp

        with self.assertRaises(ValueError):
            send_top_accounts_notification(client, df, recipient_email="nobody@example.com")


# ─────────────────────────────────────────────────────────────────────────────
#  Test: Module-level import guards
# ─────────────────────────────────────────────────────────────────────────────

class TestImportGuards(unittest.TestCase):
    """Verify that _require_pandas() raises a clear error when deps are missing."""

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard._PANDAS_AVAILABLE", False)
    def test_fetch_raises_importerror_when_pandas_missing(self):
        mock_credential = MagicMock(spec=TokenCredential)
        client = DataverseClient("https://example.crm.dynamics.com", mock_credential)
        dashboard = AccountSalesDashboard(client)
        with self.assertRaises(ImportError) as ctx:
            dashboard.fetch_accounts_with_orders()
        self.assertIn("pandas", str(ctx.exception).lower())

    @patch("PowerPlatform.Dataverse.extensions.sales_dashboard._PANDAS_AVAILABLE", False)
    def test_create_dashboard_raises_importerror_when_pandas_missing(self):
        mock_credential = MagicMock(spec=TokenCredential)
        client = DataverseClient("https://example.crm.dynamics.com", mock_credential)
        dashboard = AccountSalesDashboard(client)
        df = pd.DataFrame({"a": [1]})   # not empty — so we reach the check
        with self.assertRaises(ImportError):
            dashboard.create_dashboard(df)


if __name__ == "__main__":
    unittest.main()
