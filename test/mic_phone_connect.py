"""音频设备连通性快速检查脚本。"""

import sounddevice as sd


def main() -> None:
    devices = sd.query_devices()
    default_input, default_output = sd.default.device
    print(f"default_input={default_input}, default_output={default_output}")
    for idx, dev in enumerate(devices):
        name = dev.get("name", "")
        max_in = dev.get("max_input_channels", 0)
        max_out = dev.get("max_output_channels", 0)
        print(f"[{idx}] {name} in={max_in} out={max_out}")


if __name__ == "__main__":
    main()