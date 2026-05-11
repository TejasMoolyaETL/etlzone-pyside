"""API details list, create, and view pages."""

from app.api_dev.api_details.api_details_copy_to_api_mgmt import CopyApiDevToMgmtPage
from app.api_dev.api_details.api_details_create import CreateAPIDetailPage
from app.api_dev.api_details.api_details_list import APIDetailsPage
from app.api_dev.api_details.api_details_view import ViewAPIDetailPage

__all__ = [
    "APIDetailsPage",
    "CopyApiDevToMgmtPage",
    "CreateAPIDetailPage",
    "ViewAPIDetailPage",
]
