"""The tests for UVC camera module."""
from datetime import datetime
import socket
from unittest.mock import MagicMock, call, patch

import pytest
import requests
from uvcclient import camera as camera, nvr

from homeassistant.components.camera import SUPPORT_STREAM
from homeassistant.components.uvc import camera as uvc
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.setup import async_setup_component


@pytest.fixture(name="mock_remote")
def mock_remote_fixture(camera_info):
    """Mock the nvr.UVCRemote class."""
    with patch("homeassistant.components.uvc.camera.nvr.UVCRemote") as mock_remote:
        mock_remote.return_value.get_camera.return_value = camera_info
        yield mock_remote


@pytest.fixture(name="camera_info")
def camera_info_fixture():
    """Mock the camera info of a camera."""
    return {
        "model": "UVC",
        "recordingSettings": {
            "fullTimeRecordEnabled": True,
            "motionRecordEnabled": False,
        },
        "host": "host-a",
        "internalHost": "host-b",
        "username": "admin",
        "channels": [
            {
                "id": "0",
                "width": 1920,
                "height": 1080,
                "fps": 25,
                "bitrate": 6000000,
                "isRtspEnabled": True,
                "rtspUris": [
                    "rtsp://host-a:7447/uuid_rtspchannel_0",
                    "rtsp://foo:7447/uuid_rtspchannel_0",
                ],
            },
            {
                "id": "1",
                "width": 1024,
                "height": 576,
                "fps": 15,
                "bitrate": 1200000,
                "isRtspEnabled": False,
                "rtspUris": [
                    "rtsp://host-a:7447/uuid_rtspchannel_1",
                    "rtsp://foo:7447/uuid_rtspchannel_1",
                ],
            },
        ],
    }


async def test_setup_full_config(hass, mock_remote, camera_info):
    """Test the setup with full configuration."""
    config = {
        "platform": "uvc",
        "nvr": "foo",
        "password": "bar",
        "port": 123,
        "key": "secret",
    }
    mock_cameras = [
        {"uuid": "one", "name": "Front", "id": "id1"},
        {"uuid": "two", "name": "Back", "id": "id2"},
        {"uuid": "three", "name": "Old AirCam", "id": "id3"},
    ]

    def mock_get_camera(uuid):
        """Create a mock camera."""
        if uuid == "id3":
            camera_info["model"] = "airCam"

        return camera_info

    mock_remote.return_value.index.return_value = mock_cameras
    mock_remote.return_value.get_camera.side_effect = mock_get_camera
    mock_remote.return_value.server_version = (3, 2, 0)

    assert await async_setup_component(hass, "camera", {"camera": config})
    await hass.async_block_till_done()

    assert mock_remote.call_count == 1
    assert mock_remote.call_args == call("foo", 123, "secret", ssl=False)

    camera_states = hass.states.async_all("camera")

    assert len(camera_states) == 2

    state = hass.states.get("camera.front")

    assert state
    assert state.name == "Front"

    state = hass.states.get("camera.back")

    assert state
    assert state.name == "Back"

    entity_registry = async_get_entity_registry(hass)
    entity_entry = entity_registry.async_get("camera.front")

    assert entity_entry.unique_id == "id1"

    entity_entry = entity_registry.async_get("camera.back")

    assert entity_entry.unique_id == "id2"


async def test_setup_partial_config(hass, mock_remote):
    """Test the setup with partial configuration."""
    config = {"platform": "uvc", "nvr": "foo", "key": "secret"}
    mock_cameras = [
        {"uuid": "one", "name": "Front", "id": "id1"},
        {"uuid": "two", "name": "Back", "id": "id2"},
    ]
    mock_remote.return_value.index.return_value = mock_cameras
    mock_remote.return_value.server_version = (3, 2, 0)

    assert await async_setup_component(hass, "camera", {"camera": config})
    await hass.async_block_till_done()

    assert mock_remote.call_count == 1
    assert mock_remote.call_args == call("foo", 7080, "secret", ssl=False)

    camera_states = hass.states.async_all("camera")

    assert len(camera_states) == 2

    state = hass.states.get("camera.front")

    assert state
    assert state.name == "Front"

    state = hass.states.get("camera.back")

    assert state
    assert state.name == "Back"

    entity_registry = async_get_entity_registry(hass)
    entity_entry = entity_registry.async_get("camera.front")

    assert entity_entry.unique_id == "id1"

    entity_entry = entity_registry.async_get("camera.back")

    assert entity_entry.unique_id == "id2"


@patch("uvcclient.nvr.UVCRemote")
@patch.object(uvc, "UnifiVideoCamera")
async def test_setup_partial_config_v31x(mock_uvc, mock_remote, hass):
    """Test the setup with a v3.1.x server."""
    config = {"platform": "uvc", "nvr": "foo", "key": "secret"}
    mock_cameras = [
        {"uuid": "one", "name": "Front", "id": "id1"},
        {"uuid": "two", "name": "Back", "id": "id2"},
    ]
    mock_remote.return_value.index.return_value = mock_cameras
    mock_remote.return_value.get_camera.return_value = {"model": "UVC"}
    mock_remote.return_value.server_version = (3, 1, 3)

    assert await async_setup_component(hass, "camera", {"camera": config})
    await hass.async_block_till_done()

    assert mock_remote.call_count == 1
    assert mock_remote.call_args == call("foo", 7080, "secret", ssl=False)
    mock_uvc.assert_has_calls(
        [
            call(mock_remote.return_value, "one", "Front", "ubnt"),
            call(mock_remote.return_value, "two", "Back", "ubnt"),
        ]
    )


@patch.object(uvc, "UnifiVideoCamera")
async def test_setup_incomplete_config(mock_uvc, hass):
    """Test the setup with incomplete configuration."""
    assert await async_setup_component(
        hass, "camera", {"platform": "uvc", "nvr": "foo"}
    )
    await hass.async_block_till_done()

    assert not mock_uvc.called
    assert await async_setup_component(
        hass, "camera", {"platform": "uvc", "key": "secret"}
    )
    await hass.async_block_till_done()

    assert not mock_uvc.called
    assert await async_setup_component(
        hass, "camera", {"platform": "uvc", "port": "invalid"}
    )
    await hass.async_block_till_done()

    assert not mock_uvc.called


@patch.object(uvc, "UnifiVideoCamera")
@patch("uvcclient.nvr.UVCRemote")
@pytest.mark.parametrize(
    "error", [nvr.NotAuthorized, nvr.NvrError, requests.exceptions.ConnectionError]
)
async def test_setup_nvr_errors_during_indexing(mock_remote, mock_uvc, hass, error):
    """Set up test for NVR errors during indexing."""
    config = {"platform": "uvc", "nvr": "foo", "key": "secret"}
    mock_remote.return_value.index.side_effect = error
    assert await async_setup_component(hass, "camera", {"camera": config})
    await hass.async_block_till_done()

    assert not mock_uvc.called
    if error in [nvr.NvrError, requests.exceptions.ConnectionError]:
        pytest.raises(PlatformNotReady)


@patch.object(uvc, "UnifiVideoCamera")
@patch("uvcclient.nvr.UVCRemote.__init__")
@pytest.mark.parametrize(
    "error", [nvr.NotAuthorized, nvr.NvrError, requests.exceptions.ConnectionError]
)
async def test_setup_nvr_errors_during_initialization(
    mock_remote, mock_uvc, hass, error
):
    """Set up test for NVR errors during initialization."""
    config = {"platform": "uvc", "nvr": "foo", "key": "secret"}
    mock_remote.return_value = None
    mock_remote.side_effect = error
    assert await async_setup_component(hass, "camera", {"camera": config})
    await hass.async_block_till_done()

    assert not mock_remote.index.called
    assert not mock_uvc.called

    if error in [nvr.NvrError, requests.exceptions.ConnectionError]:
        pytest.raises(PlatformNotReady)


@pytest.fixture
def uvc_fixture():
    """Set up the mock camera."""
    nvr = MagicMock()
    uuid = "uuid"
    name = "name"
    password = "seekret"
    _uvc = uvc.UnifiVideoCamera(nvr, uuid, name, password)
    nvr.get_camera.return_value = {
        "model": "UVC Fake",
        "recordingSettings": {"fullTimeRecordEnabled": True},
        "host": "host-a",
        "internalHost": "host-b",
        "username": "admin",
        "channels": [
            {
                "id": "0",
                "width": 1920,
                "height": 1080,
                "fps": 25,
                "bitrate": 6000000,
                "isRtspEnabled": True,
                "rtspUris": [
                    "rtsp://host-a:7447/uuid_rtspchannel_0",
                    "rtsp://foo:7447/uuid_rtspchannel_0",
                ],
            },
            {
                "id": "1",
                "width": 1024,
                "height": 576,
                "fps": 15,
                "bitrate": 1200000,
                "isRtspEnabled": False,
                "rtspUris": [
                    "rtsp://host-a:7447/uuid_rtspchannel_1",
                    "rtsp://foo:7447/uuid_rtspchannel_1",
                ],
            },
        ],
    }
    nvr.server_version = (3, 2, 0)
    nvr._host = "foo"

    _uvc.update()
    return _uvc


async def test_properties(uvc_fixture):
    """Test the properties."""
    assert "name" == uvc_fixture.name
    assert uvc_fixture.is_recording
    assert "Ubiquiti" == uvc_fixture.brand
    assert "UVC Fake" == uvc_fixture.model
    assert SUPPORT_STREAM == uvc_fixture.supported_features


@patch("uvcclient.camera.UVCCameraClientV320")
async def test_motion_recording_mode_properties(mock_camera, uvc_fixture):
    """Test the properties."""
    mock_camera.get_camera.return_value["recordingSettings"][
        "fullTimeRecordEnabled"
    ] = False
    mock_camera.get_camera.return_value["recordingSettings"][
        "motionRecordEnabled"
    ] = True
    assert not uvc_fixture.is_recording
    assert (
        datetime(2021, 1, 8, 1, 56, 32, 367000)
        == uvc_fixture.extra_state_attributes["last_recording_start_time"]
    )

    mock_camera.get_camera.return_value["recordingIndicator"] = "DISABLED"
    assert not uvc_fixture.is_recording

    mock_camera.get_camera.return_value["recordingIndicator"] = "MOTION_INPROGRESS"
    assert uvc_fixture.is_recording

    mock_camera.get_camera.return_value["recordingIndicator"] = "MOTION_FINISHED"
    assert uvc_fixture.is_recording


async def test_stream(uvc_fixture):
    """Test the RTSP stream URI."""
    stream_source = await uvc_fixture.stream_source()

    assert stream_source == "rtsp://foo:7447/uuid_rtspchannel_0"


@patch("uvcclient.store.get_info_store")
@patch("uvcclient.camera.UVCCameraClientV320")
async def test_login(mock_camera, mock_store, uvc_fixture):
    """Test the login."""
    uvc_fixture._login()
    assert mock_camera.call_count == 1
    assert mock_camera.call_args == call("host-a", "admin", "seekret")
    assert mock_camera.return_value.login.call_count == 1
    assert mock_camera.return_value.login.call_args == call()


@patch("uvcclient.store.get_info_store")
@patch("uvcclient.camera.UVCCameraClient")
async def test_login_v31x(mock_camera, mock_store, uvc_fixture):
    """Test login with v3.1.x server."""
    uvc_fixture._nvr.server_version = (3, 1, 3)
    uvc_fixture._login()
    assert mock_camera.call_count == 1
    assert mock_camera.call_args == call("host-a", "admin", "seekret")
    assert mock_camera.return_value.login.call_count == 1
    assert mock_camera.return_value.login.call_args == call()


@patch("uvcclient.store.get_info_store")
@patch("uvcclient.camera.UVCCameraClientV320")
async def test_login_tries_both_addrs_and_caches(mock_camera, mock_store, uvc_fixture):
    """Test the login tries."""
    responses = [0]

    def mock_login(*a):
        """Mock login."""
        try:
            responses.pop(0)
            raise OSError
        except IndexError:
            pass

    mock_store.return_value.get_camera_password.return_value = None
    mock_camera.return_value.login.side_effect = mock_login
    uvc_fixture._login()
    assert 2 == mock_camera.call_count
    assert "host-b" == uvc_fixture._connect_addr

    mock_camera.reset_mock()
    uvc_fixture._login()
    assert mock_camera.call_count == 1
    assert mock_camera.call_args == call("host-b", "admin", "seekret")
    assert mock_camera.return_value.login.call_count == 1
    assert mock_camera.return_value.login.call_args == call()


@patch("uvcclient.store.get_info_store")
@patch("uvcclient.camera.UVCCameraClientV320")
async def test_login_fails_both_properly(mock_camera, mock_store, uvc_fixture):
    """Test if login fails properly."""
    mock_camera.return_value.login.side_effect = socket.error
    assert uvc_fixture._login() is None
    assert uvc_fixture._connect_addr is None


async def test_camera_image_tries_login_bails_on_failure(uvc_fixture):
    """Test retrieving failure."""
    with patch.object(uvc_fixture, "_login") as mock_login:
        mock_login.return_value = False
        assert uvc_fixture.camera_image() is None
        assert mock_login.call_count == 1
        assert mock_login.call_args == call()


async def test_camera_image_logged_in(uvc_fixture):
    """Test the login state."""
    uvc_fixture._camera = MagicMock()
    assert uvc_fixture._camera.get_snapshot.return_value == uvc_fixture.camera_image()


async def test_camera_image_error(uvc_fixture):
    """Test the camera image error."""
    uvc_fixture._camera = MagicMock()
    uvc_fixture._camera.get_snapshot.side_effect = camera.CameraConnectError
    assert uvc_fixture.camera_image() is None


async def test_camera_image_reauths(uvc_fixture):
    """Test the re-authentication."""
    responses = [0]

    def mock_snapshot():
        """Mock snapshot."""
        try:
            responses.pop()
            raise camera.CameraAuthError()
        except IndexError:
            pass
        return "image"

    uvc_fixture._camera = MagicMock()
    uvc_fixture._camera.get_snapshot.side_effect = mock_snapshot
    with patch.object(uvc_fixture, "_login") as mock_login:
        assert "image" == uvc_fixture.camera_image()
        assert mock_login.call_count == 1
        assert mock_login.call_args == call()
        assert [] == responses


async def test_camera_image_reauths_only_once(uvc_fixture):
    """Test if the re-authentication only happens once."""
    uvc_fixture._camera = MagicMock()
    uvc_fixture._camera.get_snapshot.side_effect = camera.CameraAuthError
    with patch.object(uvc_fixture, "_login") as mock_login:
        with pytest.raises(camera.CameraAuthError):
            uvc_fixture.camera_image()
        assert mock_login.call_count == 1
        assert mock_login.call_args == call()
