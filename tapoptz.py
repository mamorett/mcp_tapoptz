import os
import datetime
import logging
import sys
import asyncio
import socket
import traceback
from typing import Tuple, List, Optional, Any, Dict
import httpx
from onvif import ONVIFCamera as ONVIFCameraClient
from zeep.transports import Transport
from zeep.cache import InMemoryCache
from fastmcp import FastMCP

# Configure logging to stderr for MCP compatibility and visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("mcp-tapoptz")
# Set zeep logging to see transport issues
logging.getLogger('zeep.transports').setLevel(logging.INFO)

class ONVIFCamera:
    """
    Module for controlling cameras using ONVIF
    """

    def __init__(self, ip: str, port: int, username: str, password: str):
        logger.info(f"Attempting reachability check for {ip}:{port}...")
        try:
            with socket.create_connection((ip, port), timeout=5):
                logger.info(f"Port {port} is open and reachable.")
        except Exception as e:
            logger.error(f"Reachability check failed: {e}")
            raise ConnectionError(f"Cannot reach camera at {ip}:{port}. Is the IP correct and the camera online?")

        logger.info(f"Connecting to ONVIF service...")
        
        # Use InMemoryCache and explicit timeouts to avoid file system or network hangs
        transport = Transport(timeout=10, operation_timeout=10, cache=InMemoryCache())
        
        try:
            self.camera = ONVIFCameraClient(
                ip, 
                port, 
                username, 
                password, 
                transport=transport
            )
            
            # Create services
            logger.info("Initializing PTZ service...")
            self.ptz = self.camera.create_ptz_service()
            
            logger.info("Initializing Media service...")
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
            
        except Exception as e:
            logger.error(f"Failed during ONVIF initialization: {traceback.format_exc()}")
            raise

    def absolute_move(self, pan: float, tilt: float, zoom: float) -> dict:
        request = self.ptz.create_type('AbsoluteMove')
        request.ProfileToken = self.token
        request.Position = {
            'PanTilt': {'x': pan, 'y': tilt}, 
            'Zoom': {'x': zoom}
        }
        self.ptz.AbsoluteMove(request)
        return {"status": "success", "action": "absolute_move", "pan": pan, "tilt": tilt, "zoom": zoom}

    def continuous_move(self, pan: float, tilt: float, zoom: float) -> dict:
        request = self.ptz.create_type('ContinuousMove')
        request.ProfileToken = self.token
        request.Velocity = {
            'PanTilt': {'x': pan, 'y': tilt}, 
            'Zoom': {'x': zoom}
        }
        self.ptz.ContinuousMove(request)
        return {"status": "success", "action": "continuous_move", "pan_speed": pan, "tilt_speed": tilt, "zoom_speed": zoom}

    def relative_move(self, pan: float, tilt: float, zoom: float) -> dict:
        request = self.ptz.create_type('RelativeMove')
        request.ProfileToken = self.token
        request.Translation = {
            'PanTilt': {'x': pan, 'y': tilt}, 
            'Zoom': {'x': zoom}
        }
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

    def get_ptz_status(self) -> dict:
        request = self.ptz.create_type('GetStatus')
        request.ProfileToken = self.token
        ptz_status = self.ptz.GetStatus(request)
        
        status = {"pan": 0.0, "tilt": 0.0, "zoom": 0.0}
        if ptz_status and hasattr(ptz_status, 'Position') and ptz_status.Position:
            pos = ptz_status.Position
            if hasattr(pos, 'PanTilt') and pos.PanTilt:
                status["pan"] = getattr(pos.PanTilt, "x", 0.0)
                status["tilt"] = getattr(pos.PanTilt, "y", 0.0)
            if hasattr(pos, 'Zoom') and pos.Zoom:
                status["zoom"] = getattr(pos.Zoom, "x", 0.0)
        return status

    def set_preset(self, preset_name: str) -> dict:
        presets = self._get_presets_complete()
        if presets:
            for preset in presets:
                if hasattr(preset, 'Name') and str(preset.Name) == preset_name:
                    return {"status": "ignored", "message": f"Preset '{preset_name}' already exists"}

        request = self.ptz.create_type('SetPreset')
        request.ProfileToken = self.token
        request.PresetName = preset_name
        self.ptz.SetPreset(request)
        return {"status": "success", "action": "set_preset", "name": preset_name}

    def get_presets(self) -> List[Tuple[int, str]]:
        ptz_get_presets = self._get_presets_complete()
        presets = []
        if ptz_get_presets:
            for i, preset in enumerate(ptz_get_presets):
                name = getattr(preset, 'Name', f"Preset_{i}")
                presets.append((i, str(name)))
        return presets

    def _get_presets_complete(self):
        try:
            request = self.ptz.create_type('GetPresets')
            request.ProfileToken = self.token
            return self.ptz.GetPresets(request)
        except Exception as e:
            logger.warning(f"Failed to get presets: {e}")
            return []

    def remove_preset(self, preset_name: str) -> dict:
        presets = self._get_presets_complete()
        request = self.ptz.create_type('RemovePreset')
        request.ProfileToken = self.token
        for preset in presets:
            if hasattr(preset, 'Name') and str(preset.Name) == preset_name:
                request.PresetToken = preset.token
                self.ptz.RemovePreset(request)
                return {"status": "success", "action": "remove_preset", "name": preset_name}
        return {"status": "error", "message": f"Preset '{preset_name}' not found"}

    def go_to_preset(self, preset_name: str) -> dict:
        presets = self._get_presets_complete()
        request = self.ptz.create_type('GotoPreset')
        request.ProfileToken = self.token
        for preset in presets:
            if hasattr(preset, 'Name') and str(preset.Name) == preset_name:
                request.PresetToken = preset.token
                self.ptz.GotoPreset(request)
                return {"status": "success", "action": "go_to_preset", "name": preset_name}
        return {"status": "error", "message": f"Preset '{preset_name}' not found"}

    async def capture_snapshot(self, output_dir: str = "/tmp") -> dict:
        """
        Capture a still JPEG snapshot and save it to output_dir.
        """
        try:
            logger.info("Requesting snapshot URI from camera...")
            # We wrap the sync media call in a thread
            def get_uri():
                req = self.media.create_type('GetSnapshotUri')
                req.ProfileToken = self.token
                return self.media.GetSnapshotUri(req)
                
            res = await asyncio.to_thread(get_uri)
            
            if not res or not hasattr(res, 'Uri') or not res.Uri:
                return {"status": "error", "message": "Camera did not return a snapshot URI."}
            
            uri = res.Uri
            logger.info(f"Snapshot URI obtained: {uri}")

            # Download the image using Digest Auth
            auth = httpx.DigestAuth(self.username, self.password)
            async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                logger.info(f"Downloading snapshot from {uri}...")
                try:
                    response = await client.get(uri, auth=auth)
                    if response.status_code == 401:
                        logger.warning("Digest authentication failed, attempting without authentication...")
                        response = await client.get(uri)
                except Exception as net_err:
                    logger.error(f"Network error downloading snapshot: {net_err}")
                    return {"status": "error", "message": f"Network error: {str(net_err)}"}
                
                response.raise_for_status()
                
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"snapshot_{timestamp}.jpg"
                abs_output_dir = os.path.abspath(output_dir)
                os.makedirs(abs_output_dir, exist_ok=True)
                filepath = os.path.join(abs_output_dir, filename)
                
                logger.info(f"Writing {len(response.content)} bytes to {filepath}...")
                with open(filepath, "wb") as f:
                    f.write(response.content)
                
                return {
                    "status": "success", 
                    "action": "capture_snapshot",
                    "path": filepath,
                    "size": len(response.content),
                    "uri": uri
                }
        except Exception as e:
            logger.error(f"Snapshot capture failed: {traceback.format_exc()}")
            # Return more info in the message
            err_type = type(e).__name__
            err_msg = str(e) if str(e) else "No error message"
            return {"status": "error", "message": f"Snapshot failed [{err_type}]: {err_msg}"}

# --- MCP Server & Global State ---

mcp = FastMCP("Tapo PTZ")
_camera_instance: Optional[ONVIFCamera] = None
_conn_lock = asyncio.Lock()

async def get_camera() -> ONVIFCamera:
    """Lazy initialize the camera connection in a thread-safe way."""
    global _camera_instance
    async with _conn_lock:
        if _camera_instance is None:
            ip = os.getenv("TAPO_IP")
            port_env = os.getenv("TAPO_PORT", "2020")
            try:
                port = int(port_env)
            except ValueError:
                port = 2020
                
            username = os.getenv("TAPO_USERNAME")
            password = os.getenv("TAPO_PASSWORD")
            
            if not all([ip, username, password]):
                raise ValueError("TAPO_IP, TAPO_USERNAME, and TAPO_PASSWORD environment variables must be set.")
            
            try:
                logger.info("Initializing camera connection...")
                _camera_instance = await asyncio.to_thread(ONVIFCamera, ip, port, username, password)
            except Exception as e:
                logger.error(f"Failed to connect to camera: {traceback.format_exc()}")
                raise RuntimeError(f"Connection failed: {str(e)}")
                
        return _camera_instance

async def call_with_timeout(func_name, *args, **kwargs):
    cam = await get_camera()
    try:
        target_func = getattr(cam, func_name)
        return await asyncio.wait_for(asyncio.to_thread(target_func, *args, **kwargs), timeout=15.0)
    except asyncio.TimeoutError:
        logger.error(f"Operation {func_name} timed out after 15s")
        return {"status": "error", "message": f"Operation {func_name} timed out."}
    except Exception as e:
        logger.error(f"Error during {func_name}: {traceback.format_exc()}")
        err_msg = str(e) if str(e) else f"Unknown {type(e).__name__}"
        return {"status": "error", "message": err_msg}

@mcp.tool()
async def absolute_move(pan: float, tilt: float, zoom: float) -> dict:
    """Move to absolute PTZ position (pan/tilt -1 to 1, zoom 0 to 1)."""
    return await call_with_timeout("absolute_move", pan, tilt, zoom)

@mcp.tool()
async def continuous_move(pan: float, tilt: float, zoom: float) -> dict:
    """Start continuous movement at given speeds (typically -1.0 to 1.0)."""
    return await call_with_timeout("continuous_move", pan, tilt, zoom)

@mcp.tool()
async def relative_move(pan: float, tilt: float, zoom: float) -> dict:
    """Move relative to the current position."""
    return await call_with_timeout("relative_move", pan, tilt, zoom)

@mcp.tool()
async def stop_move() -> dict:
    """Stop all PTZ movement."""
    return await call_with_timeout("stop_move")

@mcp.tool()
async def set_home_position() -> dict:
    """Save current position as the camera's home."""
    return await call_with_timeout("set_home_position")

@mcp.tool()
async def go_home_position() -> dict:
    """Return the camera to its home position."""
    return await call_with_timeout("go_home_position")

@mcp.tool()
async def get_ptz_status() -> dict:
    """Query current PTZ coordinates."""
    return await call_with_timeout("get_ptz_status")

@mcp.tool()
async def set_preset(preset_name: str) -> dict:
    """Save current position as a named preset."""
    return await call_with_timeout("set_preset", preset_name)

@mcp.tool()
async def get_presets() -> List[Tuple[int, str]]:
    """List all saved presets."""
    res = await call_with_timeout("get_presets")
    return res if isinstance(res, list) else []

@mcp.tool()
async def remove_preset(preset_name: str) -> dict:
    """Delete a named preset."""
    return await call_with_timeout("remove_preset", preset_name)

@mcp.tool()
async def go_to_preset(preset_name: str) -> dict:
    """Move the camera to a saved preset."""
    return await call_with_timeout("go_to_preset", preset_name)

@mcp.tool()
async def capture_snapshot(output_dir: str = "/tmp") -> dict:
    """Grab a still JPEG snapshot from the camera and save it locally."""
    try:
        cam = await get_camera()
        return await asyncio.wait_for(cam.capture_snapshot(output_dir), timeout=30.0)
    except Exception as e:
        logger.error(f"Snapshot tool failed: {traceback.format_exc()}")
        return {"status": "error", "message": f"Snapshot tool error: {str(e)}"}

@mcp.tool()
async def diagnostic_check() -> dict:
    """Perform a comprehensive diagnostic check of the camera and server."""
    diag = {
        "timestamp": datetime.datetime.now().isoformat(),
        "env": {
            "TAPO_IP": os.getenv("TAPO_IP"),
            "TAPO_PORT": os.getenv("TAPO_PORT", "2020"),
            "TAPO_USERNAME": os.getenv("TAPO_USERNAME") is not None,
            "TAPO_PASSWORD": os.getenv("TAPO_PASSWORD") is not None,
        }
    }
    try:
        cam = await get_camera()
        diag["connection"] = "connected"
        diag["profile_token"] = cam.token
        try:
            status = await asyncio.to_thread(cam.get_ptz_status)
            diag["ptz_status_raw"] = status
        except Exception as e:
            diag["ptz_status_error"] = str(e)
            
        try:
            presets = await asyncio.to_thread(cam.get_presets)
            diag["presets_count"] = len(presets)
        except Exception as e:
            diag["presets_error"] = str(e)
            
    except Exception as e:
        diag["connection_error"] = str(e)
        
    return diag

def main():
    mcp.run()

if __name__ == "__main__":
    main()
