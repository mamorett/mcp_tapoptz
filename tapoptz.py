import os
import datetime
import logging
from typing import Tuple, List, Optional
import httpx
from onvif import ONVIFCamera as ONVIFCameraClient
from fastmcp import FastMCP

# Configure logging to stderr for MCP compatibility
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-tapoptz")

class ONVIFCamera:
    """
    Module for controlling cameras using ONVIF
    """

    def __init__(self, ip: str, port: int, username: str, password: str):
        logger.info(f"Connecting to camera at {ip}:{port}...")
        self.camera = ONVIFCameraClient(ip, port, username, password)
        self.ptz = self.camera.create_ptz_service()
        self.media = self.camera.create_media_service()
        self.username = username
        self.password = password

        # Fetch the first profile token
        logger.info("Fetching media profiles...")
        profiles = self.media.GetProfiles()
        if not profiles:
            raise Exception("No media profiles found on camera")
        self.token = profiles[0].token
        logger.info(f"Connected successfully. Using profile token: {self.token}")

    def absolute_move(self, pan: float, tilt: float, zoom: float) -> dict:
        request = self.ptz.create_type('AbsoluteMove')
        request.ProfileToken = self.token
        request.Position = {'PanTilt': {'x': pan, 'y': tilt}, 'Zoom': zoom}
        self.ptz.AbsoluteMove(request)
        return {"status": "success", "action": "absolute_move", "pan": pan, "tilt": tilt, "zoom": zoom}

    def continuous_move(self, pan: float, tilt: float, zoom: float) -> dict:
        request = self.ptz.create_type('ContinuousMove')
        request.ProfileToken = self.token
        request.Velocity = {'PanTilt': {'x': pan, 'y': tilt}, 'Zoom': zoom}
        self.ptz.ContinuousMove(request)
        return {"status": "success", "action": "continuous_move", "pan_speed": pan, "tilt_speed": tilt, "zoom_speed": zoom}

    def relative_move(self, pan: float, tilt: float, zoom: float) -> dict:
        request = self.ptz.create_type('RelativeMove')
        request.ProfileToken = self.token
        request.Translation = {'PanTilt': {'x': pan, 'y': tilt}, 'Zoom': zoom}
        self.ptz.RelativeMove(request)
        return {"status": "success", "action": "relative_move", "pan_delta": pan, "tilt_delta": tilt, "zoom_delta": zoom}

    def stop_move(self) -> dict:
        request = self.ptz.create_type('Stop')
        request.ProfileToken = self.token
        self.ptz.Stop(request)
        return {"status": "success", "action": "stop_move"}

    def set_home_position(self) -> dict:
        request = self.ptz.create_type('SetHomePosition')
        request.ProfileToken = self.token
        self.ptz.SetHomePosition(request)
        self.ptz.Stop({'ProfileToken': self.token})
        return {"status": "success", "action": "set_home_position"}

    def go_home_position(self) -> dict:
        request = self.ptz.create_type('GotoHomePosition')
        request.ProfileToken = self.token
        self.ptz.GotoHomePosition(request)
        return {"status": "success", "action": "go_home_position"}

    def get_ptz_status(self) -> Tuple[float, float, float]:
        request = self.ptz.create_type('GetStatus')
        request.ProfileToken = self.token
        ptz_status = self.ptz.GetStatus(request)
        pan = ptz_status.Position.PanTilt.x
        tilt = ptz_status.Position.PanTilt.y
        zoom = ptz_status.Position.Zoom.x
        return pan, tilt, zoom

    def set_preset(self, preset_name: str) -> dict:
        presets = self._get_presets_complete()
        for preset in presets:
            if str(preset.Name) == preset_name:
                return {"status": "ignored", "message": f"Preset '{preset_name}' already exists"}

        request = self.ptz.create_type('SetPreset')
        request.ProfileToken = self.token
        request.PresetName = preset_name
        self.ptz.SetPreset(request)
        return {"status": "success", "action": "set_preset", "name": preset_name}

    def get_presets(self) -> List[Tuple[int, str]]:
        ptz_get_presets = self._get_presets_complete()
        presets = []
        for i, preset in enumerate(ptz_get_presets):
            presets.append((i, str(preset.Name)))
        return presets

    def _get_presets_complete(self):
        request = self.ptz.create_type('GetPresets')
        request.ProfileToken = self.token
        return self.ptz.GetPresets(request)

    def remove_preset(self, preset_name: str) -> dict:
        presets = self._get_presets_complete()
        request = self.ptz.create_type('RemovePreset')
        request.ProfileToken = self.token
        for preset in presets:
            if str(preset.Name) == preset_name:
                request.PresetToken = preset.token
                self.ptz.RemovePreset(request)
                return {"status": "success", "action": "remove_preset", "name": preset_name}
        return {"status": "error", "message": f"Preset '{preset_name}' not found"}

    def go_to_preset(self, preset_name: str) -> dict:
        presets = self._get_presets_complete()
        request = self.ptz.create_type('GotoPreset')
        request.ProfileToken = self.token
        for preset in presets:
            if str(preset.Name) == preset_name:
                request.PresetToken = preset.token
                self.ptz.GotoPreset(request)
                return {"status": "success", "action": "go_to_preset", "name": preset_name}
        return {"status": "error", "message": f"Preset '{preset_name}' not found"}

    async def capture_snapshot(self, output_dir: str = "/tmp") -> str:
        request = self.media.create_type('GetSnapshotUri')
        request.ProfileToken = self.token
        res = self.media.GetSnapshotUri(request)
        uri = res.Uri

        auth = httpx.DigestAuth(self.username, self.password)
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(uri, auth=auth)
            response.raise_for_status()
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"snapshot_{timestamp}.jpg"
            filepath = os.path.join(output_dir, filename)
            
            os.makedirs(output_dir, exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(response.content)
            
            return os.path.abspath(filepath)

# --- MCP Server & Lazy Init ---

mcp = FastMCP("Tapo PTZ")
_camera_instance: Optional[ONVIFCamera] = None

def get_camera() -> ONVIFCamera:
    """Lazy initialize the camera connection."""
    global _camera_instance
    if _camera_instance is None:
        ip = os.getenv("TAPO_IP")
        port = int(os.getenv("TAPO_PORT", "2020"))
        username = os.getenv("TAPO_USERNAME")
        password = os.getenv("TAPO_PASSWORD")
        
        if not all([ip, username, password]):
            raise ValueError("TAPO_IP, TAPO_USERNAME, and TAPO_PASSWORD environment variables must be set.")
        
        try:
            _camera_instance = ONVIFCamera(ip, port, username, password)
        except Exception as e:
            logger.error(f"Failed to connect to camera: {e}")
            raise RuntimeError(f"Could not connect to camera at {ip}:{port}. Verify IP and ONVIF credentials.")
            
    return _camera_instance

@mcp.tool()
def absolute_move(pan: float, tilt: float, zoom: float) -> dict:
    """Move to absolute PTZ position (pan/tilt -1 to 1, zoom 0 to 1)."""
    return get_camera().absolute_move(pan, tilt, zoom)

@mcp.tool()
def continuous_move(pan: float, tilt: float, zoom: float) -> dict:
    """Start continuous movement at given speeds (typically -1.0 to 1.0)."""
    return get_camera().continuous_move(pan, tilt, zoom)

@mcp.tool()
def relative_move(pan: float, tilt: float, zoom: float) -> dict:
    """Move relative to the current position."""
    return get_camera().relative_move(pan, tilt, zoom)

@mcp.tool()
def stop_move() -> dict:
    """Stop all PTZ movement."""
    return get_camera().stop_move()

@mcp.tool()
def set_home_position() -> dict:
    """Save current position as the camera's home."""
    return get_camera().set_home_position()

@mcp.tool()
def go_home_position() -> dict:
    """Return the camera to its home position."""
    return get_camera().go_home_position()

@mcp.tool()
def get_ptz_status() -> dict:
    """Query current PTZ coordinates. Returns {"pan": float, "tilt": float, "zoom": float}."""
    pan, tilt, zoom = get_camera().get_ptz_status()
    return {"pan": pan, "tilt": tilt, "zoom": zoom}

@mcp.tool()
def set_preset(preset_name: str) -> dict:
    """Save current position as a named preset."""
    return get_camera().set_preset(preset_name)

@mcp.tool()
def get_presets() -> List[Tuple[int, str]]:
    """List all saved presets as (index, name)."""
    return get_camera().get_presets()

@mcp.tool()
def remove_preset(preset_name: str) -> dict:
    """Delete a named preset."""
    return get_camera().remove_preset(preset_name)

@mcp.tool()
def go_to_preset(preset_name: str) -> dict:
    """Move the camera to a saved preset."""
    return get_camera().go_to_preset(preset_name)

@mcp.tool()
async def capture_snapshot(output_dir: str = "/tmp") -> str:
    """Grab a still JPEG snapshot from the camera and save it locally."""
    return await get_camera().capture_snapshot(output_dir)

def main():
    # Run the server immediately. Connection happens on first tool call.
    mcp.run()

if __name__ == "__main__":
    main()
