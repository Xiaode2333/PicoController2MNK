# Pico Controller Mappings

## 通用行为

- Pico BOOTSEL 单击：配置 `1 -> 2 -> 3 -> 1` 轮换。
- Pico BOOTSEL 双击：开关 Pico 的键鼠输出。
- Pico BOOTSEL 长按 `2s`，或在配置软件的 **Settings** 页点击 **Calibrate center + auto-detect deadzone**：启动右摇杆中心/死区校准。接下来 `10s` 内保持右摇杆不动，Pico 会用这段时间的 raw RX/RY 均值作为中心，并把测到的静止抖动量自动设为右摇杆死区。软件会显示倒计时和结果；点击 **Save to board** 后校准值会持久保存。
- **Virtual DPI** 是所有配置共用的鼠标计数倍率，可设为 `100`-`20000`，当前出厂默认值为 `5000`；`1000` 保持旧版速度。USB HID 不会把 DPI 标签发送给游戏；若要在保持转身速度的同时提高细腻度，请提高 Virtual DPI，并相应降低游戏内鼠标灵敏度。
- Hold 判定：`200ms`。
- 配置软件可为每个 Combo 动作设置激活延迟：`0` 表示立即激活，`1`-`65535` 表示等待指定毫秒数后持续按住输出，任一必需输入松开时同步释放。例如新建仅要求 LT、抑制 LT 普通输出、输出 `Left Shift`、延迟 `500ms` 的 Combo，即可在按住 LT 半秒后自动屏息。
- 双击判定：`250ms`。
- Tap 输出时间：`40ms`。
- Turbo 滚轮：`30Hz`。
- 组合滚轮：`LB + RB + Dpad up` 为鼠标滚轮上 `10Hz`；`LB + RB + Dpad down` 为鼠标滚轮下 `10Hz`，并抑制 LB/RB 与对应 Dpad 的普通输出。
- USB 输出：键盘和鼠标使用独立 HID interface/endpoint；每个 endpoint 的 full-speed HID poll 仍是 `1ms`，mapper 内部 readiness 检查为 `8000Hz`。
- 接收座断连保护：如果手柄关机后接收座持续发送全 `0x00` 输入包，或持续发送“只有 Dpad up、其他输入空闲”的假包，Pico 会当作无效输入并释放键鼠输出，避免误判成 Dpad up。
- 鼠标按键释放宽限：当前出厂默认 `0ms`。可为任意输入映射出的左/右/中键设置释放宽限；组合键主动抑制、显式切换配置、关闭输出或真正断连仍会立即释放。旧存储 schema 中恰好等于旧默认 `12ms` 的值仍会迁移到 `40ms`，以保持旧配置兼容；`0` 和其他用户自定义值保持不变。
- 左摇杆：`0.10` 死区；配置 1/3 为 8 向 WASD，配置 2 为 4 向 WASD；只在方向状态变化时发送按下/松开。
- 右摇杆：基础死区 `0.02`，默认校准中心为 X `2014` / Y `2043`；BOOTSEL 长按校准后会改为自动测到的中心和静止抖动死区。
- 诊断固件：`pico_kbm_mapper_trace.uf2` 运行与正式固件相同的可配置 mapper 动作引擎，同时打开 CDC 状态/capture，供 `tools/diagnose_button_flash.py` 抓鼠标按键闪断。
- 双鼠标模式：配置软件的 **Settings** 页可分别设置模式 1/2 的灵敏度倍率和右摇杆死区。在任意已识别输入的 Tap 动作中选择 **Toggle mouse mode + key**（PUBG 捡物菜单可选 `Tab`）；软件会自动清空该输入的 Hold 动作，并把 Double tap 设为 **Swap mouse modes**。单击会发送所选键并在两套鼠标参数之间切换；双击只交换两套模式的逻辑顺序、不发送键，用来在游戏菜单状态与当前鼠标模式不同步时校正。启用 Double tap 后，单击必须等双击判定窗口结束才会输出。
- Dpad left：`B`。
- Menu：`Tab`。
- 截图键短按：调用默认 `Macro 1 (Snapshot Alt+RMB)`，执行 `Left Alt` down -> `30ms` -> 鼠标右键 down -> `10ms` -> 鼠标右键 up -> `30ms` -> `Left Alt` up。
- 配置 1 的 LB/RB 默认映射为 `Q`/`E`，LT/RT 默认映射为鼠标右键/左键；配置 2/3 保持 LB/RB 为鼠标右键/左键。
- Y：鼠标中键。
- Rstick click：单击在 `1`/`2` 间交替。配置 1/3 hold 为 `X`，配置 2 hold 为 `3`。

## 默认宏

| 宏槽 | 名称 | 触发方式 | 默认内容 |
| --- | --- | --- | --- |
| Macro 1 | `Snapshot Alt+RMB` | On press | `Left Alt` down `30ms` -> 鼠标右键 down `10ms` -> 鼠标右键 up `30ms` -> `Left Alt` up |
| Macro 2 | `Alt+MB Right` | On press | `Left Alt` down `50ms` -> 鼠标右键 down `50ms` |
| Macro 3-8 | `Macro 3` ... `Macro 8` | On press | 空，供用户录制或编辑 |

## 配置 1

| 输入 | 输出 |
| --- | --- |
| 左摇杆 | 8 向 `W/A/S/D` |
| 右摇杆 | 鼠标移动，`5000 px/s * raw input` |
| Dpad up | 单击 `5`，hold `G` |
| Dpad right | `` ` `` |
| Dpad down | 单击 `3`，hold `4` |
| Dpad left | `B` |
| LB | `Q` |
| RB | `E` |
| LT | 鼠标右键 |
| RT | 鼠标左键 |
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

`LB + RB` 前缀组合会抑制 LB/RB、face button 或对应 Dpad 的普通输出；`LT + RT` 的 `Left Shift` 不抑制 LT/RT，因此会与两个扳机的鼠标按键输出同时生效。

| 输入 | 输出 |
| --- | --- |
| LB + RB + X | `Ctrl + 1` |
| LB + RB + Y | `Ctrl + 2` |
| LB + RB + A | `Ctrl + 3` |
| LB + RB + B | `Ctrl + 4` |
| LB + RB + Dpad left | `Macro 2 (Alt+MB Right)` |
| LB + RB + Dpad right | `H` |
| LB + RB + Dpad up | 鼠标滚轮上，`10Hz` |
| LB + RB + Dpad down | 鼠标滚轮下，`10Hz` |
| LT（持续 `500ms`） | `Left Shift`，不抑制 LT 的鼠标右键输出；松开 LT 时同步释放 |

## 配置 2

| 输入 | 输出 |
| --- | --- |
| 左摇杆 | 4 向 `W/A/S/D` |
| 右摇杆，未按 Aim（腰射） | 鼠标移动，X `5000 px/s`，Y `4166 px/s` |
| 右摇杆，按住 Aim（ADS） | 鼠标移动，X `3750 px/s`，Y `2000 px/s` |
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

`LB + RB` 前缀组合会抑制 LB/RB、face button 或对应 Dpad 的普通输出；其余组合的抑制范围见下表说明。

| 输入 | 输出 |
| --- | --- |
| LB + RB + X | `Ctrl + 1` |
| LB + RB + Y | `Ctrl + 2` |
| LB + RB + A | `Ctrl + 3` |
| LB + RB + B | `Ctrl + 4` |
| LB + RB + Dpad up | 鼠标滚轮上，`10Hz` |
| LB + RB + Dpad down | 鼠标滚轮下，`10Hz` |
| Lstick click + Y | `Z`，并抑制 Y 的鼠标中键 |
| LB + B | `Left Shift`，并抑制 B 的滚轮下 |
| LB + Dpad down | `H`，并抑制 Dpad down 的滚轮上 |

### 配置 2 右摇杆外圈加速

Aim / ADS 输入可在配置软件的 **Edit stick rules...** 中选择，例如 LT。
旧配置默认使用 RB；固件 2.4.0 起支持修改。该选择只决定 ADS 速度和加速
何时生效，不会更改这个输入原有的键鼠映射。按住所选输入时进入 ADS，
松开后恢复腰射；更换按键后保存配置即可。

| 条件 | 行为 |
| --- | --- |
| 未按 Aim，右摇杆外圈 `>= 0.95` | X 速度从 `5000` 开始，在 `0.3s` 内额外增加到 `+4583` |
| 按住 Aim，右摇杆外圈 `>= 0.95` | 等待 `0.25s` 后，在 `1.0s` 内 X/Y 额外增加到 `+625/+625` |
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

`LT + RT` 会抑制 LT/RT 的普通映射；`LB + RB + Dpad` 滚轮组合使用独立的前缀。

| 输入 | 输出 |
| --- | --- |
| LB + RB + Dpad up | 鼠标滚轮上，`10Hz` |
| LB + RB + Dpad down | 鼠标滚轮下，`10Hz` |
| LT + RT | `X`，并抑制 LT/RT 的普通映射 |
| LB + B | `U`，并抑制 B 的普通映射 |
| LB + LT | `Q`，并抑制 LT 的普通映射 |
| LB + RT | `E`，并抑制 RT 的普通映射 |

## 可配置的输入事件和输出状态（固件 2.5.0）

按键和组合键的识别时机与输出方式分别设置。即时输入或延迟 Hold 可选择
持续有效、按下沿（Pressed）、松开沿（Released）；短 Click 要求使用即时识别，
并在全局 Hold 阈值之前松开。Tap / Double tap 栏位本身已经是识别后的手势。

普通键、修饰键组合、双键、鼠标按钮和滚轮可选择 Hold、Toggle、Click、
Pressed 锁定或 Released 释放匹配的锁定输出。默认 Hold 维持 HID 按下状态，
不需要持续重复发送按下报告。例如 LB+RB → Left Alt，选择延迟 0、持续有效输入、
Hold 输出，任一参与键松开才释放 Alt。Click 时长为 1–4095 ms，0 使用全局 Tap
时长；离散输入事件配合 Hold 输出也会产生 Click。滚轮 Click 只滚动一格。

Toggle 再次触发关闭；Pressed 锁定可由动作类型及键/按钮相同的 Released 动作
释放。Stop macros / release toggles 清除所有锁定和宏；切配置、关闭输出及输入
失效也会清除。组合抑制会取消参与输入的状态。Click 在报告真正送出后计时，
连续 Click 会排队并确保两次按下之间已送出释放报告。

宏绑定可继承宏的默认播放方式，也可独立指定按下播放一次、松开播放一次、
按住循环或 Toggle 循环。按住循环在松开时立即停止。宏按键/鼠标步骤设置对应
设备的状态，Delay 保持现有状态；可插入键盘释放或鼠标释放步骤形成单击。
宏播放及结束时保留其他仍然按住的普通键、修饰键和鼠标按钮，滚轮映射也继续
运行；USB 键盘仍最多同时输出六个普通键。宏的相对鼠标移动在播放时优先于摇杆。
