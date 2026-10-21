from unittest.mock import patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def mock_bluetooth_stack():
    """Don't start Home Assistant's real Bluetooth/USB components in tests.

    They depend on the machine (BlueZ, D-Bus, USB), which differs between CI
    runner images; the tests fake the Bluetooth client themselves.
    """
    with patch("homeassistant.components.bluetooth.async_setup", return_value=True), patch(
        "homeassistant.components.bluetooth_adapters.async_setup", return_value=True, create=True
    ), patch("homeassistant.components.usb.async_setup", return_value=True):
        yield
