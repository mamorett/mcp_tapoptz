# 📹 mcp-tapoptz

[![MCP](https://img.shields.io/badge/MCP-Protocol-blue)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

An [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that provides **Pan-Tilt-Zoom (PTZ)** control and **Snapshot** capabilities for TP-Link Tapo (and other ONVIF-compatible) cameras.

Easily move your camera, manage presets, and capture still images directly from your favorite AI assistant or any MCP client.

## ✨ Features

- 🏎️ **PTZ Control**: Absolute, Relative, and Continuous movement.
- 📍 **Preset Management**: Save, go to, and remove named camera positions.
- 🏠 **Home Position**: Quickly set or return to your camera's "home" base.
- 📸 **Snapshots**: Capture still JPEG images and save them locally.
- 🔌 **ONVIF Support**: Works with Tapo cameras (C200, C210, C500, etc.) and most ONVIF-compliant devices.

---

## 🚀 Installation

The easiest way to run `mcp-tapoptz` is using `uvx`.

```bash
# Set your environment variables
export TAPO_IP="192.168.1.50"
export TAPO_USERNAME="your_onvif_user"
export TAPO_PASSWORD="your_onvif_password"

# Run the server
uvx mcp-tapoptz
```

### Configuration for Claude Desktop

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tapo-ptz": {
      "command": "uvx",
      "args": ["mcp-tapoptz"],
      "env": {
        "TAPO_IP": "192.168.1.50",
        "TAPO_PORT": "2020",
        "TAPO_USERNAME": "your_onvif_user",
        "TAPO_PASSWORD": "your_onvif_password"
      }
    }
  }
}
```

---

## 🛠️ Tools Catalog

### 🕹️ Movement

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `absolute_move` | `pan`, `tilt`, `zoom` | Move to an absolute coordinate (Pan/Tilt: -1 to 1, Zoom: 0 to 1). |
| `relative_move` | `pan`, `tilt`, `zoom` | Move relative to the current position. |
| `continuous_move` | `pan`, `tilt`, `zoom` | Start moving at a specific speed until `stop_move` is called. |
| `stop_move` | *(none)* | Immediately halt all camera movement. |

### 📍 Positions & Presets

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `get_ptz_status` | *(none)* | Get current Pan, Tilt, and Zoom coordinates. |
| `go_home_position` | *(none)* | Move the camera to its defined Home position. |
| `set_home_position` | *(none)* | Set the current camera view as the Home position. |
| `set_preset` | `preset_name` | Save the current position as a named preset. |
| `get_presets` | *(none)* | List all saved presets on the camera. |
| `go_to_preset` | `preset_name` | Move the camera to a previously saved preset. |
| `remove_preset` | `preset_name` | Delete a named preset. |

### 📸 Imaging

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `capture_snapshot` | `output_dir` (optional) | Grab a still JPEG from the camera and save it to the specified directory (defaults to `/tmp`). |

---

## ⚙️ Environment Variables

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `TAPO_IP` | **Yes** | - | The local IP address of your Tapo camera. |
| `TAPO_USERNAME` | **Yes** | - | Your camera's ONVIF username (set in the Tapo App). |
| `TAPO_PASSWORD` | **Yes** | - | Your camera's ONVIF password (set in the Tapo App). |
| `TAPO_PORT` | No | `2020` | The ONVIF service port (usually 2020 for Tapo). |

---

## 📋 Prerequisites

1.  **Enable ONVIF**: Open the Tapo app, go to `Camera Settings` -> `Advanced Settings` -> `Camera Account`, and create an account. This is the username/password you use for `TAPO_USERNAME` and `TAPO_PASSWORD`.
2.  **Network Visibility**: Ensure the machine running this MCP server can reach the camera's IP address on the specified port.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
