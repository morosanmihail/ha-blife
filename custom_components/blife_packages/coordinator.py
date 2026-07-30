"""Data coordinator for BLife Packages integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AUTH_BASE_URL,
    AUTH_LOGIN_PATH,
    CONF_API_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PACKAGES_QUERY = """
query($after: String) {
  packages(first: 50, after: $after) {
    nodes {
      id
      reference
      status
      createdDate
      collectedDate
    }
    pageInfo { hasNextPage endCursor }
  }
}
""".strip()


@dataclass
class Package:
    """Representation of a package."""

    package_id: str
    reference: str
    status: str
    created_date: datetime | None = None
    collected_date: datetime | None = None
    access_code: str | None = None
    locker_description: str | None = None
    tracking_number: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert package to dictionary for attributes."""
        return {
            "package_id": self.package_id,
            "reference": self.reference,
            "code": self.reference,
            "status": self.status,
            "created_date": self.created_date.isoformat() if self.created_date else None,
            "collected_date": self.collected_date.isoformat() if self.collected_date else None,
            "access_code": self.access_code,
            "locker_description": self.locker_description,
            "tracking_number": self.tracking_number,
        }


@dataclass
class BLifePackagesData:
    """Data class for BLife packages state."""

    firstname: str
    packages: list[Package] = field(default_factory=list)
    last_updated: datetime | None = None

    @property
    def packages_ready_to_collect(self) -> int:
        """Return count of packages pending collection."""
        return len([p for p in self.packages if p.status == "pending"])

    @property
    def packages_list(self) -> list[dict[str, Any]]:
        """Return list of packages as dictionaries."""
        return [p.to_dict() for p in self.packages]


class BLifePackagesCoordinator(DataUpdateCoordinator[BLifePackagesData]):
    """Coordinator for fetching BLife packages data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=config_entry,
        )
        self.username = config_entry.data[CONF_USERNAME]
        self.password = config_entry.data[CONF_PASSWORD]
        self.firstname = config_entry.data.get("firstname", "User")
        self._token: str | None = config_entry.data.get("token")
        self._token_type: str = config_entry.data.get("token_type", "Bearer")
        self._api_url: str | None = config_entry.data.get(CONF_API_URL)

    async def _async_update_data(self) -> BLifePackagesData:
        """Fetch data from API."""
        try:
            return await self._fetch_packages_data()
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Error fetching packages data: {err}") from err

    async def _fetch_packages_data(self) -> BLifePackagesData:
        """Fetch packages via GraphQL."""
        if not self._token or not self._api_url:
            await self._authenticate()

        url = f"{self._api_url}/query"
        headers = {
            "Authorization": f"{self._token_type} {self._token}",
            "x-spike-origin": "mobile",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                data = await self._graphql_request(session, url, headers)
                if data is None:
                    _LOGGER.warning("Token expired, re-authenticating...")
                    await self._authenticate()
                    headers["Authorization"] = f"{self._token_type} {self._token}"
                    data = await self._graphql_request(session, url, headers)
                    if data is None:
                        raise ConfigEntryAuthFailed(
                            "Authentication failed. Please reconfigure the integration."
                        )

                nodes = list((data.get("packages") or {}).get("nodes") or [])
                page_info = (data.get("packages") or {}).get("pageInfo") or {}
                page = 1
                while page_info.get("hasNextPage"):
                    page += 1
                    cursor = page_info.get("endCursor")
                    data = await self._graphql_request(session, url, headers, after=cursor)
                    if data is None:
                        raise ConfigEntryAuthFailed(
                            "Authentication failed. Please reconfigure the integration."
                        )
                    nodes.extend((data.get("packages") or {}).get("nodes") or [])
                    page_info = (data.get("packages") or {}).get("pageInfo") or {}

                packages = self._parse_packages_response({"packages": {"nodes": nodes}})
                _LOGGER.info(
                    "Fetched %d package(s) across %d page(s) from %s (%d pending)",
                    len(packages.packages),
                    page,
                    url,
                    packages.packages_ready_to_collect,
                )
                await self._enrich_pending_packages(session, headers, packages)
                return packages
        except ConfigEntryAuthFailed:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.info("GraphQL request to %s failed: %s", url, err)
            raise UpdateFailed(f"Connection error: {err}") from err

    async def _graphql_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        headers: dict,
        after: str | None = None,
    ) -> dict | None:
        """Make GraphQL request, return None on 401."""
        _LOGGER.info("Calling GraphQL endpoint %s (after=%s)", url, after)
        async with session.post(
            url,
            headers=headers,
            json={"query": PACKAGES_QUERY, "variables": {"after": after}},
        ) as response:
            _LOGGER.info("GraphQL endpoint %s responded with status %d", url, response.status)
            if response.status == 401:
                return None
            if response.status != 200:
                body = await response.text()
                raise UpdateFailed(f"GraphQL endpoint returned {response.status}: {body}")
            body = await response.json(content_type=None)
            if errors := body.get("errors"):
                _LOGGER.info("GraphQL endpoint %s returned errors: %s", url, errors)
                raise UpdateFailed(f"GraphQL errors: {errors}")
            return body.get("data") or {}

    async def _authenticate(self) -> None:
        """Authenticate against Spike auth service."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-spike-origin": "mobile",
        }

        login_url = f"{AUTH_BASE_URL}{AUTH_LOGIN_PATH}"
        _LOGGER.info("Authenticating against %s", login_url)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                login_url,
                headers=headers,
                json={"email": self.username, "password": self.password},
            ) as response:
                body = await response.json(content_type=None)
                _LOGGER.info("Authentication call to %s responded with status %d", login_url, response.status)

                if response.status == 401:
                    raise ConfigEntryAuthFailed("Invalid credentials")
                if response.status != 200:
                    raise UpdateFailed(f"Login failed with status {response.status}")
                if isinstance(body, dict) and not body.get("success", True):
                    errors = body.get("errors") or []
                    raise ConfigEntryAuthFailed(errors[0] if errors else "Login rejected")

                value = (body.get("value") or {}) if isinstance(body, dict) else {}
                token = value.get("token")
                if not token:
                    raise UpdateFailed(f"No token in login response: {list(body.keys())}")

                self._token = token
                self._token_type = value.get("type") or "Bearer"
                _LOGGER.info("Authentication succeeded, token type %s", self._token_type)

                if not self._api_url:
                    await self._fetch_api_url()

    async def _fetch_api_url(self) -> None:
        """Fetch community apiUrl from user-access endpoint."""
        headers = {
            "Authorization": f"{self._token_type} {self._token}",
            "x-spike-origin": "mobile",
            "Accept": "application/json",
        }
        user_access_url = f"{AUTH_BASE_URL}/api/user-access"
        _LOGGER.info("Calling %s", user_access_url)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                user_access_url,
                headers=headers,
            ) as response:
                body = await response.json(content_type=None)
                _LOGGER.info("%s responded with status %d", user_access_url, response.status)
                if response.status != 200:
                    raise UpdateFailed(f"user-access returned {response.status}")

                clients = (body.get("value") or {}).get("clients") or []
                if not clients:
                    raise UpdateFailed("No clients in user-access response")

                raw_url = clients[0].get("apiUrl", "")
                if not raw_url:
                    raise UpdateFailed("No apiUrl in client entry")

                if raw_url.startswith("http"):
                    self._api_url = raw_url
                elif "localhost" in raw_url:
                    self._api_url = f"https://{raw_url}"
                else:
                    self._api_url = f"https://api-{raw_url}"

                _LOGGER.info("Resolved api_url: %s", self._api_url)

    async def _enrich_pending_packages(
        self,
        session: aiohttp.ClientSession,
        headers: dict,
        packages_data: BLifePackagesData,
    ) -> None:
        """Fetch access code and locker details for pending packages via REST."""
        for package in packages_data.packages:
            if package.status != "pending":
                continue
            try:
                detail_url = f"{self._api_url}/mobile/v1/delivery/{package.package_id}"
                _LOGGER.info("Fetching delivery detail for package %s", package.package_id)
                async with session.get(detail_url, headers=headers) as resp:
                    _LOGGER.info(
                        "Delivery detail fetch for package %s responded with status %d",
                        package.package_id,
                        resp.status,
                    )
                    if resp.status != 200:
                        continue
                    detail = (await resp.json(content_type=None)).get("value") or {}
                    package.access_code = detail.get("accessCode")
                    for cfv in detail.get("customFieldValues") or []:
                        field_name = cfv.get("fieldName") or ""
                        cid = cfv.get("customFieldId", "")
                        val = cfv.get("value")
                        if cid == "e1c552a9-3929-48da-8c40-49b460c67cc6" or "locker" in field_name.lower():
                            package.locker_description = str(val) if val is not None else None
                        elif cid == "40306110-2b9c-4b30-8d25-7243b293096d" or "tracking" in field_name.lower():
                            package.tracking_number = str(val) if val is not None else None
            except Exception as err:  # noqa: BLE001
                _LOGGER.info("Failed to enrich package %s: %s", package.package_id, err)

    def _parse_packages_response(self, data: dict[str, Any]) -> BLifePackagesData:
        """Parse GraphQL response into BLifePackagesData."""
        nodes = (data.get("packages") or {}).get("nodes") or []
        packages = []

        for item in nodes:
            created_date = None
            if cd := item.get("createdDate"):
                try:
                    created_date = datetime.fromisoformat(str(cd).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            collected_date = None
            if cod := item.get("collectedDate"):
                try:
                    collected_date = datetime.fromisoformat(str(cod).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            packages.append(Package(
                package_id=str(item.get("id", "")),
                reference=str(item.get("reference", "")),
                status=str(item.get("status") or "unknown"),
                created_date=created_date,
                collected_date=collected_date,
            ))

        return BLifePackagesData(
            firstname=self.firstname,
            packages=packages,
            last_updated=datetime.now(),
        )
