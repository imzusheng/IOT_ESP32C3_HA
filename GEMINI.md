# GEMINI Project Analysis: ESP32-C3 MicroPython IoT

## 🚀 Project Overview

- 全程使用中文

This is a comprehensive MicroPython IoT project designed for the ESP32-C3 microcontroller, with a focus on integration into a Home Assistant ecosystem. The project is architected with modularity and resilience in mind, addressing the challenges of a memory-constrained embedded environment.

**Core Technologies:**
*   **Firmware:** MicroPython on ESP32-C3
*   **Connectivity:** WiFi (with multi-network support)
*   **Communication Protocol:** MQTT for IoT messaging
*   **Configuration:**
    *   Primary: A central Python dictionary in `src/config.py` for static configuration.
    *   User-facing: A sophisticated Web Bluetooth interface (`web/index.html`) for dynamic configuration of WiFi, MQTT, and device settings.
*   **Build/Deployment:** A custom Python script (`build.py`) using `mpy-cross` for compilation and `mpremote` for deployment.

**Key Architectural Features:**
*   **State Machine (`src/lib/sys/fsm.py`):** Manages the device's operational state (INIT, NETWORKING, RUNNING, ERROR, etc.) for predictable behavior.
*   **System Daemon (`src/sys_daemon.py`):** A background task that monitors system health, including CPU temperature and memory usage, and controls status LEDs.
*   **Error Recovery (`src/lib/sys/erm.py`):** A dedicated manager for handling and recovering from various errors (network, memory, hardware), enhancing stability.
*   **Memory Management (`src/lib/sys/memo.py`):** Employs object pooling and other optimization techniques to minimize memory allocation and garbage collection overhead, which is critical on the ESP32-C3's limited SRAM.
*   **Hardware Watchdog:** Prevents system lockups by automatically rebooting the device if the main loop becomes unresponsive.

---

## 🛠️ Building and Running

The project uses a powerful custom build script, `build.py`, which automates compilation and deployment.

**Prerequisites:**
1.  **Python 3:** To run the build script.
2.  **mpy-cross:** The MicroPython cross-compiler. Must be in your system's PATH.
3.  **mpremote:** The official MicroPython remote control tool. Install with `pip install mpremote`.

**Key Commands:**

*   **Compile the project:**
    *   This cross-compiles `.py` files in `src/` to more efficient `.mpy` bytecode and places the output in the `dist/` directory.
    ```bash
    python build.py --compile
    ```

*   **Build and Deploy (Default Action):**
    *   This is the most common workflow. It compiles the project and then uploads only the changed files to the connected ESP32 device. After uploading, it resets the device and starts monitoring its serial output.
    ```bash
    python build.py
    ```

*   **Upload Only (Smart Sync):**
    *   Uploads the contents of the `dist/` directory, skipping any files that haven't changed since the last upload (based on a local MD5 cache).
    ```bash
    python build.py --upload
    ```

*   **Force Full Upload:**
    *   To ignore the cache and upload all files from `dist/`, combine `--full-upload` with an upload action.
    ```bash
    python build.py --upload --full-upload
    ```

*   **Clean Device and Upload:**
    *   To completely wipe the filesystem on the device before uploading.
    ```bash
    python build.py --clean --upload
    ```

*   **Monitor Device Output:**
    *   Connect to the device's serial port to view `print()` statements and logs in real-time.
    ```bash
    python build.py --monitor
    ```

*   **Connect to REPL:**
    *   Open an interactive MicroPython REPL session with the device.
    ```bash
    python build.py --repl
    ```

*   **Specifying the Port:**
    *   The script attempts to auto-detect the ESP32 port. If it fails or you have multiple devices, you can specify it manually:
    ```bash
    python build.py -p COM3
    ```

---

## 📖 Development Conventions

*   **Configuration:** All core, non-volatile configuration is centralized in `src/config.py`. This avoids filesystem I/O on the device and makes default settings clear. Comments in this file explain the impact of each setting.
*   **Modularity:** The code is well-structured into modules with clear responsibilities (e.g., `net_wifi.py` for WiFi, `net_mqtt.py` for MQTT).
*   **Memory First:** The code shows a strong emphasis on memory optimization. This includes using object pools (`memo.py`), `bytearray` for string concatenation, and careful management of object creation in loops. New development should adhere to these practices.
*   **Logging:** A custom logger is used. The log level can be configured in `src/config.py`.
*   **Web-based Configuration:** For user-facing settings, the preferred method is the Web Bluetooth interface in `web/index.html`. This provides a user-friendly experience without requiring a serial connection.
*   **Build System:** All deployment and compilation should be done through `build.py` to ensure consistency and correctness. Avoid manually copying files to the device.
*   **Excluding Files:** Test files and other non-essential code are excluded from the build by default (see `DEFAULT_EXCLUDE_DIRS` in `build.py`).
