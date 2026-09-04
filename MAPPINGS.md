# Pico Controller Mappings

## 通用行为

- Pico BOOTSEL 单击：配置 `1 -> 2 -> 3 -> 1` 轮换。
- Pico BOOTSEL 双击：开关 Pico 的键鼠输出。
- Pico BOOTSEL 长按 `2s`，或在配置软件的 **Settings** 页点击 **Calibrate center + auto-detect deadzone**：启动右摇杆中心/死区校准。接下来 `10s` 内保持右摇杆不动，Pico 会用这段时间的 raw RX/RY 均值作为中心，并把测到的静止抖动量自动设为右摇杆死区。软件会显示倒计时和结果；点击 **Save to board** 后校准值会持久保存。
- **Virtual DPI** 是所有配置共用的鼠标计数倍率，可设为 `100`-`20000`：`1000` 保持旧版速度，`2000` 将右摇杆产生的鼠标计数翻倍。USB HID 不会把 DPI 标签发送给游戏；若要在保持转身速度的同时提高细腻度，请提高 Virtual DPI，并相应降低游戏内鼠标灵敏度。
- Hold 判定：`200ms`。
- 双击判定：`250ms`。
- Tap 输出时间：`40ms`。
- Turbo 滚轮：`30Hz`。
- 组合滚轮：`LT + RT + Dpad up` 为鼠标滚轮上 `10Hz`；`LT + RT + Dpad down` 为鼠标滚轮下 `10Hz`，并抑制 LT/RT 与对应 Dpad 的普通输出。
- USB 输出：键盘和鼠标使用独立 HID interface/endpoint；每个 endpoint 的 full-speed HID poll 仍是 `1ms`，mapper 内部 readiness 检查为 `8000Hz`。
- 接收座断连保护：如果手柄关机后接收座持续发送全 `0x00` 输入包，或持续发送“只有 Dpad up、其他输入空闲”的假包，Pico 会当作无效输入并释放键鼠输出，避免误判成 Dpad up。
- 鼠标按键释放宽限：默认 `40ms`，作用于任意输入映射出的左/右/中键，也覆盖短暂的 input-freshness 超时；组合键主动抑制、显式切换配置、关闭输出或真正断连仍会立即释放。旧存储 schema 中恰好等于旧默认 `12ms` 的值会迁移到 `40ms`；`0` 和其他用户自定义值保持不变。
- 左摇杆：`0.10` 死区；配置 1/3 为 8 向 WASD，配置 2 为 4 向 WASD；只在方向状态变化时发送按下/松开。
- 右摇杆：基础死区 `0.06`，BOOTSEL 长按校准后会改为自动测到的静止抖动死区。
- 诊断固件：`pico_kbm_mapper_trace.uf2` 运行与正式固件相同的可配置 mapper 动作引擎，同时打开 CDC 状态/capture，供 `tools/diagnose_button_flash.py` 抓鼠标按键闪断。
- Dpad left：`B`。
- Menu：`Tab`。
- 截图键短按：调用默认 `Macro 1 (Snapshot Alt+RMB)`，执行 `Left Alt` down -> `30ms` -> 鼠标右键 down -> `10ms` -> 鼠标右键 up -> `30ms` -> `Left Alt` up。
- LB：默认映射为鼠标右键。
- RB：默认映射为鼠标左键。
- Y：鼠标中键。
- Rstick click：单击在 `1`/`2` 间交替。配置 1/3 hold 为 `X`，配置 2 hold 为 `3`。

## 默认宏

| 宏槽 | 名称 | 触发方式 | 默认内容 |
| --- | --- | --- | --- |
| Macro 1 | `Snapshot Alt+RMB` | On press | `Left Alt` down `30ms` -> 鼠标右键 down `10ms` -> 鼠标右键 up `30ms` -> `Left Alt` up |
| Macro 2-8 | `Macro 2` ... `Macro 8` | On press | 空，供用户录制或编辑 |

## 配置 1

| 输入 | 输出 |
| --- | --- |
| 左摇杆 | 8 向 `W/A/S/D` |
| 右摇杆 | 鼠标移动，`5000 px/s * raw input` |
| Dpad up | 单击 `5`，hold `G` |
| Dpad right | `` ` `` |
| Dpad down | 单击 `3`，hold `4` |
| Dpad left | `B` |
| LB | 鼠标右键 |
| RB | 鼠标左键 |
| LT | `Q` |
| RT | `E` |
| X | 单击 `R`，hold `F` |
| A | `Space` |
| B | 单击 `C`，hold `Z` |
| Y | 鼠标中键 |
| Lstick click | `Left Shift` |
| Rstick click | 单击交替 `1`/`2`，hold `X` |
| Menu | `Tab` |
| 截图键 | 短按：单次 `Left Alt` + 鼠标右键点击宏 |
| Option | 单击 `M`，hold `Esc` |

### 配置 1 组合键

这些组合键会抑制对应 face button 的普通输出；`LT + RT + Y` 会抑制 Y 的鼠标中键；Dpad 滚轮组合会抑制 LT/RT 与对应 Dpad 的普通输出；`LT + RT + Dpad left/right` 会抑制 LT/RT 与对应 Dpad 的普通输出。

| 输入 | 输出 |
| --- | --- |
| LT + RT + X | `Ctrl + 1` |
| LT + RT + Y | `Ctrl + 2` |
| LT + RT + A | `Ctrl + 3` |
| LT + RT + B | `Ctrl + 4` |
| LT + RT + Dpad left | `F4` |
| LT + RT + Dpad right | `H` |
| LT + RT + Dpad up | 鼠标滚轮上，`10Hz` |
| LT + RT + Dpad down | 鼠标滚轮下，`10Hz` |

## 配置 2

| 输入 | 输出 |
| --- | --- |
| 左摇杆 | 4 向 `W/A/S/D` |
| 右摇杆，未按 RB | 鼠标移动，X `5000 px/s`，Y `4166 px/s` |
| 右摇杆，按住 RB | 鼠标移动，X `3750 px/s`，Y `2000 px/s` |
| Dpad up | `G` |
| Dpad right | `4` |
| Dpad down，未按 LB | 鼠标滚轮上，`30Hz` turbo，没有单击/双击/hold 行为 |
| Dpad down，按住 LB | `H`，并抑制 Dpad down 的滚轮上 |
| Dpad left | `B` |
| LB | 鼠标右键 |
| RB | 鼠标左键 |
| LT | `Left Ctrl` |
| RT | `Space` |
| X | 单击 `R`，hold `E` |
| A | `V` |
| B | 鼠标滚轮下，`30Hz` turbo |
| Y | 鼠标中键 |
| Lstick click | `Q` |
| Rstick click | 单击交替 `1`/`2`，hold `3` |
| Menu | `Tab` |
| 截图键 | 短按：单次 `Left Alt` + 鼠标右键点击宏 |
| Option | 单击 `Esc`，hold `M` |

### 配置 2 组合键

这些组合键会抑制对应 face button 的普通输出；`LT + RT + Y` 会抑制 Y 的鼠标中键；Dpad 滚轮组合会抑制 LT/RT 与对应 Dpad 的普通输出。

| 输入 | 输出 |
| --- | --- |
| LT + RT + X | `Ctrl + 1` |
| LT + RT + Y | `Ctrl + 2` |
| LT + RT + A | `Ctrl + 3` |
| LT + RT + B | `Ctrl + 4` |
| LT + RT + Dpad up | 鼠标滚轮上，`10Hz` |
| LT + RT + Dpad down | 鼠标滚轮下，`10Hz` |
| Lstick click + Y | `Z`，并抑制 Y 的鼠标中键 |
| LB + B | `Left Shift`，并抑制 B 的滚轮下 |
| LB + Dpad down | `H`，并抑制 Dpad down 的滚轮上 |

### 配置 2 右摇杆外圈加速

| 条件 | 行为 |
| --- | --- |
| 未按 RB，右摇杆外圈 `>= 0.95` | X 速度从 `5000` 开始，在 `0.3s` 内额外增加到 `+4583` |
| 按住 RB，右摇杆外圈 `>= 0.95` | 等待 `0.25s` 后，在 `1.0s` 内 X/Y 额外增加到 `+625/+625` |
| 回到内圈 | 外圈加速立即清零 |

## 配置 3

| 输入 | 输出 |
| --- | --- |
| 左摇杆 | 8 向 `W/A/S/D` |
| 右摇杆 | 鼠标移动，`5000 px/s * raw input` |
| Dpad up | `L` |
| Dpad right | `5` |
| Dpad down | `H` |
| Dpad left | `B` |
| LB | 鼠标右键 |
| RB | 鼠标左键 |
| LT，未按 LB | `V` |
| RT，未按 LB | `G` |
| LT，按住 LB | `Q` |
| RT，按住 LB | `E` |
| X | 单击 `R`，双击 `F` |
| A | `Space` |
| B | 单击 `C`，hold `Z` |
| Y | 鼠标中键 |
| Lstick click | `Left Shift` |
| Rstick click | 单击交替 `1`/`2`，hold `X` |
| Menu | `Tab` |
| 截图键 | 短按：单次 `Left Alt` + 鼠标右键点击宏 |
| Option | 单击 `M`，hold `Esc` |

### 配置 3 组合键

`LT + RT` 会抑制 LT/RT 的普通映射；Dpad 滚轮组合优先于 `LT + RT` 的 `X`。

| 输入 | 输出 |
| --- | --- |
| LT + RT + Dpad up | 鼠标滚轮上，`10Hz` |
| LT + RT + Dpad down | 鼠标滚轮下，`10Hz` |
| LT + RT | `X`，并抑制 LT/RT 的普通映射 |
| LB + B | `U`，并抑制 B 的普通映射 |
| LB + LT | `Q`，并抑制 LT 的普通映射 |
| LB + RT | `E`，并抑制 RT 的普通映射 |
