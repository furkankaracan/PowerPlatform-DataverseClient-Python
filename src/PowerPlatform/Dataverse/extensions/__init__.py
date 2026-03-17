# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Optional extensions for the Dataverse SDK.
"""

from .sales_dashboard import AccountSalesDashboard, send_top_accounts_notification

__all__ = [
    "AccountSalesDashboard",
    "send_top_accounts_notification",
]
