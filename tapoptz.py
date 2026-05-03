import os
import datetime
from typing import Tuple, List, Optional
import httpx
from onvif import ONVIFCamera as ONVIFCameraClient
from fastmcp import FastMCP

class ONVIFCamera:
    """
    Module for controlling cameras using ONVIF
    """

    def __init__(self, ip: str, port: int, username: str, password: str):
        self.camera = ONVIFCameraClient(ip, port, username, password)
        self.ptz = self.camera.create_ptz_service()
        self.media = self.camera.create_media_service()
        self.username = username
        self.password = password

        # Fetch the first profile token
        profiles = self.media.GetProfiles()
        self.token = profiles[0].token

    def absolute_move(self, pan: float, tilt: float, zoom: float) -> dict:
        """
        Move pan, tilt or zoom to an absolute destination.
        Pan/Tilt usually -1.0 to 1.0, Zoom 0.0 to 1.0.
        """
        request = self.ptz.create_type('AbsoluteMove')
        request.ProfileToken = self.token
        request.Position = {'PanTilt': {'x': pan, 'y': tilt}, 'Zoom': zoom}
        self.ptz.AbsoluteMove(request)
        return {"status": "success", "action": "absolute_move", "pan": pan, "tilt": tilt, "zoom": zoom}

    def continuous_move(self, pan: float, tilt: float, zoom: float) -> dict:
        """
        Start continuous Pan/Tilt and Zoom movements at given speeds.
        Speeds usually -1.0 to 1.0.
        """
        request = self.ptz.create_type('ContinuousMove')
        request.ProfileToken = self.token
        request.Velocity = {'PanTilt': {'x': pan, 'y': tilt}, 'Zoom': zoom}
        self.ptz.ContinuousMove(request)
        return {"status": "success", "action": "continuous_move", "pan_speed": pan, "tilt_speed": tilt, "zoom_speed": zoom}

    def relative_move(self, pan: float, tilt: float, zoom: float) -> dict:
        """
        Move relative to the current position.
        """
        request = self.ptz.create_type('RelativeMove')
        request.ProfileToken = self.token
        request.Translation = {'PanTilt': {'x': pan, 'y': tilt}, 'Zoom': zoom}
        self.ptz.RelativeMove(request)
        return {"status": "success", "action": "relative_move", "pan_delta": pan, "tilt_delta": tilt, "zoom_delta": zoom}

    def stop_move(self) -> dict:
        """
        Stop ongoing pan, tilt and zoom movements.
        """
        request = self.ptz.create_type('Stop')
        request.ProfileToken = self.token
        self.ptz.Stop(request)
        return {"status": "success", "action": "stop_move"}

    def set_home_position(self) -> dict:
        """
        Save current position as the home position.
        """
        request = self.ptz.create_type('SetHomePosition')
        request.ProfileToken = self.token
        self.ptz.SetHomePosition(request)
        # Stop is often needed to finish the operation cleanly on some cameras
        self.ptz.Stop({'ProfileToken': self.token})
        return {"status": "success", "action": "set_home_position"}

    def go_home_position(self) -> dict:
        """
        Move the PTZ device to its home position.
        """
        request = self.ptz.create_type('GotoHomePosition')
        request.ProfileToken = self.token
        self.ptz.GotoHomePosition(request)
        return {"status": "success", "action": "go_home_position"}

    def get_ptz_status(self) -> Tuple[float, float, float]:
        """
        Request current PTZ status. Returns (pan, tilt, zoom).
        """
        request = self.ptz.create_type('GetStatus')
        request.ProfileToken = self.token
        ptz_status = self.ptz.GetStatus(request)
        pan = ptz_status.Position.PanTilt.x
        tilt = ptz_status.Position.PanTilt.y
        zoom = ptz_status.Position.Zoom.x
        return pan, tilt, zoom

    def set_preset(self, preset_name: str) -> dict:
        """
        Save current position as a named preset.
        """
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
        """
        List all PTZ presets as (index, name).
        """
        ptz_get_presets = self._get_presets_complete()
        presets = []
        for i, preset in enumerate(ptz_get_presets):
            presets.append((i, str(preset.Name)))
        return presets

    def _get_presets_complete(self):
        """Internal helper to get full preset objects."""
        request = self.ptz.create_type('GetPresets')
        request.ProfileToken = self.token
        return self.ptz.GetPresets(request)

    def remove_preset(self, preset_name: str) -> dict:
        """
        Remove a PTZ preset by name.
        """
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
        """
        Go to a saved preset position by name.
        """
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
        """
        Capture a still JPEG snapshot and save it to output_dir.
        """
        # Get the snapshot URI
        request = self.media.create_type('GetSnapshotUri')
        request.ProfileToken = self.token
        res = self.media.GetSnapshotUri(request)
        uri = res.Uri

        # Download the image using Digest Auth
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

# --- MCP Server ---

mcp = FastMCP("Tapo PTZ")
camera_instance: Optional[ONVIFCamera] = None

@mcp.tool()
def absolute_move(pan: float, tilt: float, zoom: float) -> dict:
    """Move to absolute PTZ position (pan/tilt -1 to 1, zoom 0 to 1)."""
    return camera_instance.absolute_move(pan, tilt, zoom)

@mcp.tool()
def continuous_move(pan: float, tilt: float, zoom: float) -> dict:
    """Start continuous movement at given speeds (typically -1.0 to 1.0)."""
    return camera_instance.continuous_move(pan, tilt, zoom)

@mcp.tool()
def relative_move(pan: float, tilt: float, zoom: float) -> dict:
    """Move relative to the current position."""
    return camera_instance.relative_move(pan, tilt, zoom)

@mcp.tool()
def stop_move() -> dict:
    """Stop all PTZ movement."""
    return camera_instance.stop_move()

@mcp.tool()
def set_home_position() -> dict:
    """Save current position as the camera's home."""
    return camera_instance.set_home_position()

@mcp.tool()
def go_home_position() -> dict:
    """Return the camera to its home position."""
    return camera_instance.go_home_position()

@mcp.tool()
def get_ptz_status() -> dict:
    """Query current PTZ coordinates. Returns {"pan": float, "tilt": float, "zoom": float}."""
    pan, tilt, zoom = camera_instance.get_ptz_status()
    return {"pan": pan, "tilt": tilt, "zoom": zoom}

@mcp.tool()
def set_preset(preset_name: str) -> dict:
    """Save current position as a named preset."""
    return camera_instance.set_preset(preset_name)

@mcp.tool()
def get_presets() -> List[Tuple[int, str]]:
    """List all saved presets as (index, name)."""
    return camera_instance.get_presets()

@mcp.tool()
def remove_preset(preset_name: str) -> dict:
    """Delete a named preset."""
    return camera_instance.remove_preset(preset_name)

@mcp.tool()
def go_to_preset(preset_name: str) -> dict:
    """Move the camera to a saved preset."""
    return camera_instance.go_to_preset(preset_name)

@mcp.tool()
async def capture_snapshot(output_dir: str = "/tmp") -> str:
    """Grab a still JPEG snapshot from the camera and save it locally."""
    return await camera_instance.capture_snapshot(output_dir)

def main():
    global camera_instance
    
    ip = os.getenv("TAPO_IP")
    port = int(os.getenv("TAPO_PORT", "2020"))
    username = os.getenv("TAPO_USERNAME")
    password = os.getenv("TAPO_PASSWORD")
    
    if not all([ip, username, password]):
        print("Error: TAPO_IP, TAPO_USERNAME, and TAPO_PASSWORD environment variables must be set.")
        return

    try:
        camera_instance = ONVIFCamera(ip, port, username, password)
        mcp.run()
    except Exception as e:
        print(f"Failed to connect to camera at {ip}:{port}: {e}")

if __name__ == "__main__":
    main()
