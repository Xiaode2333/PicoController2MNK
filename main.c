#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>


#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "pico/critical_section.h"
#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "hardware/regs/io_qspi.h"
#include "hardware/structs/ioqspi.h"
#include "hardware/structs/sio.h"
#include "hardware/sync.h"

#include "tusb.h"
#include "pio_usb.h"
#include "pio_usb_ll.h"
#include "pico/unique_id.h"
#include "mapper_config.h"
#include "mapper_action.h"
#include "mapper_calibration.h"
#include "mapper_protocol.h"


// ============================================================
// User configuration
// ============================================================

#define PIO_USB_DP_PIN 0

#ifndef PICO_FIRMWARE_MAPPER
#define PICO_FIRMWARE_MAPPER 0
#endif

#ifndef FIRMWARE_PID
#define FIRMWARE_PID 0x4005
#endif

#ifndef FIRMWARE_PRODUCT_STRING
#define FIRMWARE_PRODUCT_STRING "Pico KBM Debug Adapter"
#endif
#ifndef FIRMWARE_VERSION_MAJOR
#define FIRMWARE_VERSION_MAJOR 2u
#endif
#ifndef FIRMWARE_VERSION_MINOR
#define FIRMWARE_VERSION_MINOR 0u
#endif
#ifndef FIRMWARE_VERSION_PATCH
#define FIRMWARE_VERSION_PATCH 0u
#endif


#if PICO_FIRMWARE_MAPPER
#define MOUSE_SPEED_PX_PER_SEC 5000.0f
#else
#define MOUSE_SPEED_PX_PER_SEC 50.0f
#endif

#ifndef KEYMOUSE_REPORT_RATE_HZ
#define KEYMOUSE_REPORT_RATE_HZ 1000u
#endif

#if (KEYMOUSE_REPORT_RATE_HZ < 1u) || (KEYMOUSE_REPORT_RATE_HZ > 8000u)
#error "KEYMOUSE_REPORT_RATE_HZ must be in 1..8000"
#endif

#define KEYMOUSE_REPORT_INTERVAL_US ((1000000u + KEYMOUSE_REPORT_RATE_HZ - 1u) / KEYMOUSE_REPORT_RATE_HZ)
#define OUTPUT_DT ((float)KEYMOUSE_REPORT_INTERVAL_US / 1000000.0f)
#define USB_HID_POLL_INTERVAL_MS 1

#ifndef MAPPER_ENABLE_CDC_STATUS
#define MAPPER_ENABLE_CDC_STATUS 0
#endif

#define LEFT_DEADZONE 0.10f
#define RIGHT_DEADZONE 0.06f
#define PROFILE2_MOUSE_BASE_X 5000.0f
#define PROFILE2_MOUSE_BASE_Y 4166.0f
#define PROFILE2_MOUSE_RB_X 3750.0f
#define PROFILE2_MOUSE_RB_Y 2000.0f
#define PROFILE2_RIGHT_OUTER_THRESHOLD 0.95f
#define PROFILE2_RIGHT_OUTER_NO_RB_RAMP_US 300000u
#define PROFILE2_RIGHT_OUTER_NO_RB_EXTRA_X 4583.0f
#define PROFILE2_RIGHT_OUTER_RB_DELAY_US 250000u
#define PROFILE2_RIGHT_OUTER_RB_RAMP_US 1000000u
#define PROFILE2_RIGHT_OUTER_RB_EXTRA_X 625.0f
#define PROFILE2_RIGHT_OUTER_RB_EXTRA_Y 625.0f

#define HOLD_THRESHOLD_US 200000u
#define TAP_OUTPUT_US 40000u
#define DOUBLE_CLICK_US 250000u
#define DPAD_UP_IDLE_DISCONNECT_GUARD_US 180000u
#define TURBO_30HZ_INTERVAL_US 33333u
#define COMBO_10HZ_INTERVAL_US 100000u
#define PICO_BUTTON_SAMPLE_INTERVAL_US 5000u
#define PICO_BUTTON_DEBOUNCE_US 20000u
#define PICO_BUTTON_LONG_PRESS_US 2000000u
#define RIGHT_CALIBRATION_WINDOW_US 10000000u
#define RIGHT_CALIBRATION_SAMPLE_INTERVAL_US 1000u
#define SNAPSHOT_ALT_TO_RIGHT_DOWN_US 30000u
#define SNAPSHOT_RIGHT_DOWN_US 10000u
#define SNAPSHOT_RIGHT_UP_TO_ALT_UP_US 30000u
#define SNAPSHOT_RIGHT_UP_US (SNAPSHOT_ALT_TO_RIGHT_DOWN_US + SNAPSHOT_RIGHT_DOWN_US)
#define SNAPSHOT_TOTAL_US (SNAPSHOT_RIGHT_UP_US + SNAPSHOT_RIGHT_UP_TO_ALT_UP_US)
#define MOUSE_BUTTON_RELEASE_GRACE_US 40000u

#define INVERT_LX 0
#define INVERT_LY 0
#define INVERT_RX 0
#define INVERT_RY 0

#ifndef DEBUG_PRINT_RAW_REPORTS
#define DEBUG_PRINT_RAW_REPORTS 0
#endif

#ifndef DEBUG_PRINT_ONLY_CHANGED_REPORTS
#define DEBUG_PRINT_ONLY_CHANGED_REPORTS 1
#endif

#ifndef MAPPER_TRACE_MOUSE_OUTPUT
#define MAPPER_TRACE_MOUSE_OUTPUT 0
#endif

#define DEBUG_MAX_REPORT_LEN 64

#define CDC_COMMAND_MAX_LEN 64

#ifndef CAPTURE_SAMPLE_COUNT
#define CAPTURE_SAMPLE_COUNT 10
#endif

#ifndef CAPTURE_START_DELAY_US
#define CAPTURE_START_DELAY_US 1000000u
#endif

#ifndef CAPTURE_INTERVAL_US
#define CAPTURE_INTERVAL_US 100000u
#endif

#define HOST_AUTO_RESCAN_INTERVAL_US 1500000u

#define GAMEPAD_REPORT_TIMEOUT_US 300000u
#define MOUSE_REPORT_DT_RESET_US 100000u
#define SWITCH_INIT_STEP_DELAY_US 30000u
#define SWITCH_INIT_RETRY_DELAY_US 80000u
#define SWITCH_INIT_ACK_TIMEOUT_US 1000000u
#define SWITCH_INIT_NO_RESPONSE_DELAY_US 120000u
#define SWITCH_INIT_RESTART_DELAY_US 2000000u
#define SWITCH_OUTPUT_COMPLETE_TIMEOUT_US 200000u
#define SWITCH_INIT_MAX_RETRIES 4
#define SWITCH_INIT_OPTIONAL_RETRIES 1

#define NINTENDO_VID 0x057E
#define NINTENDO_SWITCH_PRO_PID 0x2009
#define SWITCH_PRO_NEUTRAL_BUTTON 0x008000u

#define JC_OUTPUT_RUMBLE_AND_SUBCMD 0x01
#define JC_OUTPUT_USB_CMD 0x80
#define JC_SUBCMD_REQ_DEV_INFO 0x02
#define JC_SUBCMD_SET_REPORT_MODE 0x03
#define JC_INPUT_SUBCMD_REPLY 0x21
#define JC_INPUT_IMU_DATA 0x30
#define JC_INPUT_MCU_DATA 0x31
#define JC_INPUT_USB_RESPONSE 0x81
#define JC_USB_CMD_HANDSHAKE 0x02
#define JC_USB_CMD_BAUDRATE_3M 0x03
#define JC_USB_CMD_NO_TIMEOUT 0x04
#define JC_BTN_R (1u << 6)
#define JC_BTN_L (1u << 22)

#define SW_BTN_Y          0x000001u
#define SW_BTN_X          0x000002u
#define SW_BTN_B          0x000004u
#define SW_BTN_A          0x000008u
#define SW_BTN_RB         0x000040u
#define SW_BTN_RT         0x000080u
#define SW_BTN_MENU       0x000100u
#define SW_BTN_OPTION     0x000200u
#define SW_BTN_RSTICK     0x000400u
#define SW_BTN_LSTICK     0x000800u
#define SW_BTN_SNAPSHOT   0x002000u
#define SW_BTN_DPAD_DOWN  0x010000u
#define SW_BTN_DPAD_UP    0x020000u
#define SW_BTN_DPAD_RIGHT 0x040000u
#define SW_BTN_DPAD_LEFT  0x080000u
#define SW_BTN_LB         0x400000u
#define SW_BTN_LT         0x800000u

// ============================================================
// Input report layout from your receiver
// ============================================================

#define REPORT_ID_BYTE 0

#define DPAD_BYTE 1
#define DPAD_MASK 0x0F

#define AXIS_LX_BYTE 2
#define AXIS_LY_BYTE 3
#define AXIS_RX_BYTE 4
#define AXIS_RY_BYTE 5
#define AXIS_RT_BYTE 6
#define AXIS_LT_BYTE 7

#define BUTTON_BYTE_8 8
#define BUTTON_A_MASK  0x01
#define BUTTON_B_MASK  0x02
#define BUTTON_R5_MASK 0x04
#define BUTTON_X_MASK  0x08
#define BUTTON_Y_MASK  0x10
#define BUTTON_LB_MASK 0x40
#define BUTTON_RB_MASK 0x80

#define BUTTON_BYTE_9 9
#define BUTTON_LT_DIGITAL_MASK 0x01
#define BUTTON_RT_DIGITAL_MASK 0x02
#define BUTTON_SETTING_MASK    0x04
#define BUTTON_MENU_MASK       0x08
#define BUTTON_L3_MASK         0x20
#define BUTTON_R3_MASK         0x40

// ============================================================
// Keyboard mask
// ============================================================

#define KEY_MASK_W 0x01
#define KEY_MASK_A 0x02
#define KEY_MASK_S 0x04
#define KEY_MASK_D 0x08

#ifdef MAPPER_PROFILE_COUNT
#undef MAPPER_PROFILE_COUNT
#endif

typedef enum {
    MAPPER_PROFILE_1 = 0,
    MAPPER_PROFILE_2,
    MAPPER_PROFILE_3,
    MAPPER_PROFILE_COUNT
} mapper_profile_t;
#ifndef MAPPER_PROFILE_COUNT
#define MAPPER_PROFILE_COUNT 3u
#endif


typedef enum {
    SWITCH_ACK_NONE = 0,
    SWITCH_ACK_USB,
    SWITCH_ACK_SUBCMD
} switch_ack_kind_t;

enum {
    SWITCH_INIT_IDLE = 0,
    SWITCH_INIT_USB_HANDSHAKE_1 = 1,
    SWITCH_INIT_USB_BAUDRATE = 2,
    SWITCH_INIT_USB_HANDSHAKE_2 = 3,
    SWITCH_INIT_USB_NO_TIMEOUT = 4,
    SWITCH_INIT_REQ_DEV_INFO = 5,
    SWITCH_INIT_SET_REPORT_MODE = 6,
    SWITCH_INIT_FAILED = 250
};

// ============================================================
// USB descriptors
// ============================================================

enum {
    ITF_NUM_CDC = 0,
    ITF_NUM_CDC_DATA,
    ITF_NUM_HID_KEYBOARD,
    ITF_NUM_HID_MOUSE,
    ITF_NUM_TOTAL
};

enum {
    HID_INSTANCE_KEYBOARD = 0,
    HID_INSTANCE_MOUSE = 1
};

#define EPNUM_CDC_NOTIF 0x81
#define EPNUM_CDC_OUT   0x02
#define EPNUM_CDC_IN    0x82
#define EPNUM_HID_KEYBOARD 0x83
#define EPNUM_HID_MOUSE    0x84

uint8_t const desc_hid_keyboard_report[] = {
    TUD_HID_REPORT_DESC_KEYBOARD()
};

uint8_t const desc_hid_mouse_report[] = {
    TUD_HID_REPORT_DESC_MOUSE()
};

tusb_desc_device_t const desc_device = {
    .bLength = sizeof(tusb_desc_device_t),
    .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200,

    .bDeviceClass = TUSB_CLASS_MISC,
    .bDeviceSubClass = MISC_SUBCLASS_COMMON,
    .bDeviceProtocol = MISC_PROTOCOL_IAD,

    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,

    .idVendor = 0xCafe,
    .idProduct = FIRMWARE_PID,
    .bcdDevice = 0x0100,

    .iManufacturer = 0x01,
    .iProduct = 0x02,
    .iSerialNumber = 0x03,

    .bNumConfigurations = 0x01
};

uint8_t const *tud_descriptor_device_cb(void) {
    return (uint8_t const *)&desc_device;
}

uint8_t const desc_configuration[] = {
    TUD_CONFIG_DESCRIPTOR(
        1,
        ITF_NUM_TOTAL,
        0,
        TUD_CONFIG_DESC_LEN + TUD_CDC_DESC_LEN + TUD_HID_DESC_LEN + TUD_HID_DESC_LEN,
        0,
        100
    ),

    TUD_CDC_DESCRIPTOR(
        ITF_NUM_CDC,
        4,
        EPNUM_CDC_NOTIF,
        8,
        EPNUM_CDC_OUT,
        EPNUM_CDC_IN,
        64
    ),

    TUD_HID_DESCRIPTOR(
        ITF_NUM_HID_KEYBOARD,
        0,
        HID_ITF_PROTOCOL_KEYBOARD,
        sizeof(desc_hid_keyboard_report),
        EPNUM_HID_KEYBOARD,
        CFG_TUD_HID_EP_BUFSIZE,
        USB_HID_POLL_INTERVAL_MS
    ),

    TUD_HID_DESCRIPTOR(
        ITF_NUM_HID_MOUSE,
        0,
        HID_ITF_PROTOCOL_MOUSE,
        sizeof(desc_hid_mouse_report),
        EPNUM_HID_MOUSE,
        CFG_TUD_HID_EP_BUFSIZE,
        USB_HID_POLL_INTERVAL_MS
    )
};

uint8_t const *tud_descriptor_configuration_cb(uint8_t index) {
    (void)index;
    return desc_configuration;
}

uint8_t const *tud_hid_descriptor_report_cb(uint8_t instance) {
    if (instance == HID_INSTANCE_KEYBOARD) {
        return desc_hid_keyboard_report;
    }

    if (instance == HID_INSTANCE_MOUSE) {
        return desc_hid_mouse_report;
    }

    return NULL;
}

char const *string_desc_arr[] = {
    (const char[]){0x09, 0x04},
    "Pico",
    FIRMWARE_PRODUCT_STRING,
    "000001",
    "Pico Debug CDC"
};

static uint16_t desc_str[32];

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
    (void)langid;

    uint8_t chr_count;

    if (index == 0) {
        memcpy(&desc_str[1], string_desc_arr[0], 2);
        chr_count = 1;
    } else {
        if (index >= sizeof(string_desc_arr) / sizeof(string_desc_arr[0])) {
            return NULL;
        }

        const char *str = string_desc_arr[index];
        const char *board_serial = mapper_protocol_serial();
        if (index == 3 && board_serial != NULL && board_serial[0] != '\0') {
            str = board_serial;
        }


        chr_count = strlen(str);

        if (chr_count > 31) {
            chr_count = 31;
        }

        for (uint8_t i = 0; i < chr_count; i++) {
            desc_str[1 + i] = str[i];
        }
    }

    desc_str[0] = (TUSB_DESC_STRING << 8) | (2 * chr_count + 2);

    return desc_str;
}

// ============================================================
// Shared gamepad state
// ============================================================

static volatile float g_lx = 0.0f;
static volatile float g_ly = 0.0f;
static volatile float g_rx = 0.0f;
static volatile float g_ry = 0.0f;

static volatile float g_lt_analog = 0.0f;
static volatile float g_rt_analog = 0.0f;

static volatile uint8_t g_dpad = 0x0F;

static volatile bool g_a = false;
static volatile bool g_b = false;
static volatile bool g_x = false;
static volatile bool g_y = false;
static volatile bool g_r5 = false;

static volatile bool g_lb = false;
static volatile bool g_rb = false;

static volatile bool g_lt_digital = false;
static volatile bool g_rt_digital = false;
static volatile bool g_setting = false;
static volatile bool g_menu = false;
static volatile bool g_l3 = false;
static volatile bool g_r3 = false;

static volatile uint32_t g_switch_buttons = 0;
static volatile uint16_t g_switch_raw_lx = 2048;
static volatile uint16_t g_switch_raw_ly = 2048;
static volatile uint16_t g_switch_raw_rx = 2048;
static volatile uint16_t g_switch_raw_ry = 2048;
static volatile uint16_t g_mapper_rx_center = 2048;
static volatile uint16_t g_mapper_ry_center = 2048;
static float g_mapper_right_deadzone = RIGHT_DEADZONE;
void mapper_parser_set_calibration(uint16_t rx_center, uint16_t ry_center,
                                   float right_deadzone) {
    g_mapper_rx_center = rx_center;
    g_mapper_ry_center = ry_center;
    g_mapper_right_deadzone = right_deadzone;
}


// ============================================================
// Output state
// ============================================================

static uint8_t g_last_key_mask = 0;
static uint8_t g_last_modifier = 0;
static uint8_t g_last_keycode[6] = {0, 0, 0, 0, 0, 0};
static float g_mouse_accum_x = 0.0f;
static float g_mouse_accum_y = 0.0f;
static uint8_t g_last_mouse_buttons = 0;
static uint64_t g_last_mouse_report_us = 0;
static uint64_t g_mouse_left_release_deadline_us = 0;
static uint64_t g_mouse_right_release_deadline_us = 0;
static uint64_t g_stale_mouse_release_deadline_us = 0;
static int16_t g_pending_wheel = 0;
static uint64_t g_wheel_up_next_us = 0;
static uint64_t g_wheel_down_next_us = 0;
static uint64_t g_combo_wheel_up_next_us = 0;
static uint64_t g_combo_wheel_down_next_us = 0;
static bool g_profile2_outer_active = false;
static bool g_profile2_outer_rb = false;
static uint64_t g_profile2_outer_start_us = 0;

typedef struct {
    bool pressed;
    bool hold_active;
    uint64_t press_time_us;
    uint64_t tap_until_us;
} hold_action_t;

typedef struct {
    bool pressed;
    bool waiting_single;
    bool double_active;
    uint64_t single_deadline_us;
    uint64_t tap_until_us;
    uint8_t tap_key;
} click_action_t;

typedef struct {
    bool pressed;
    bool hold_active;
    bool waiting_double;
    bool double_active;
    uint64_t press_time_us;
    uint64_t double_deadline_us;
    uint64_t tap_until_us;
} double_hold_action_t;

static hold_action_t g_hold_dpad_up = {0};
static hold_action_t g_hold_dpad_down = {0};
static hold_action_t g_hold_x = {0};
static hold_action_t g_hold_b = {0};
static hold_action_t g_hold_option = {0};
static hold_action_t g_hold_rstick = {0};
static hold_action_t g_hold_a_wheel = {0};
static click_action_t g_click_x = {0};
static double_hold_action_t g_dpad_down_wheel = {0};
static bool g_rstick_next_tap_is_1 = true;
static uint8_t g_rstick_pending_tap_key = 0;
static mapper_profile_t g_mapper_profile = MAPPER_PROFILE_1;
static bool g_mapper_output_enabled = true;
static bool g_mapper_release_pending = false;
static bool g_pico_button_raw = false;
static bool g_pico_button_stable = false;
static bool g_pico_button_click_pending = false;
static uint64_t g_pico_button_next_sample_us = 0;
static uint64_t g_pico_button_debounce_deadline_us = 0;
static uint64_t g_pico_button_click_deadline_us = 0;
static uint64_t g_pico_button_press_start_us = 0;
static bool g_pico_button_long_press_handled = false;
static bool g_snapshot_button_pressed = false;
static bool g_snapshot_macro_active = false;
static uint64_t g_snapshot_macro_start_us = 0;
static bool g_right_calibration_active = false;
static uint64_t g_right_calibration_end_us = 0;
static uint64_t g_right_calibration_next_sample_us = 0;
static uint64_t g_right_calibration_sum_rx = 0;
static uint64_t g_right_calibration_sum_ry = 0;
static uint32_t g_right_calibration_samples = 0;
static uint16_t g_right_calibration_min_rx = 4095;
static uint16_t g_right_calibration_max_rx = 0;
static uint16_t g_right_calibration_min_ry = 4095;
static uint16_t g_right_calibration_max_ry = 0;

// ============================================================
// Debug state
// ============================================================

static uint8_t g_last_report[DEBUG_MAX_REPORT_LEN];
static uint16_t g_last_report_len = 0;
static bool g_has_last_report = false;
static uint32_t g_report_count = 0;

static volatile bool g_host_stack_started = false;
static volatile bool g_host_device_mounted = false;
static volatile bool g_host_hid_mounted = false;
static volatile uint32_t g_host_mount_count = 0;
static volatile uint32_t g_host_hid_mount_count = 0;
static volatile uint32_t g_host_hid_report_count = 0;
static volatile uint32_t g_host_report_request_fail_count = 0;
static volatile uint8_t g_host_dev_addr = 0;
static volatile uint8_t g_host_hid_instance = 0;
static volatile uint8_t g_host_hid_protocol = 0;
static volatile uint16_t g_host_vid = 0;
static volatile uint16_t g_host_pid = 0;
static volatile uint32_t g_host_hid_other_report_count = 0;

static volatile bool g_gamepad_valid = false;
static volatile uint32_t g_last_valid_report_us = 0;
static uint64_t g_dpad_up_idle_guard_start_us = 0;
static bool g_dpad_up_idle_guard_blocked = false;

typedef struct {
    bool valid;
    bool hid_mounted;
    uint32_t last_report_us;
    uint32_t now_us;
} gamepad_freshness_snapshot_t;

static volatile bool g_switch_centered = false;
static volatile uint16_t g_switch_lx_center = 2048;
static volatile uint16_t g_switch_ly_center = 2048;
static volatile uint16_t g_switch_rx_center = 2048;
static volatile uint16_t g_switch_ry_center = 2048;

static volatile uint8_t g_switch_init_step = SWITCH_INIT_IDLE;
static volatile uint8_t g_switch_init_retry_count = 0;
static volatile uint8_t g_switch_subcmd_packet = 0;
static volatile uint8_t g_switch_wait_ack_kind = SWITCH_ACK_NONE;
static volatile uint8_t g_switch_wait_ack_id = 0;
static volatile uint8_t g_switch_last_usb_ack_1 = 0;
static volatile uint8_t g_switch_last_usb_ack_3 = 0;
static volatile uint8_t g_switch_last_subcmd_id = 0;
static volatile uint8_t g_switch_last_subcmd_ack = 0;
static volatile bool g_switch_output_pending = false;
static volatile uint32_t g_switch_init_send_fail_count = 0;
static volatile uint32_t g_switch_init_timeout_count = 0;
static volatile uint32_t g_switch_init_fail_count = 0;
static volatile uint32_t g_switch_usb_response_count = 0;
static volatile uint32_t g_switch_usb_ack_count = 0;
static volatile uint32_t g_switch_subcmd_response_count = 0;
static volatile uint32_t g_switch_subcmd_ack_count = 0;
static volatile uint32_t g_switch_out_submit_count = 0;
static volatile uint32_t g_switch_out_ep_submit_count = 0;
static volatile uint32_t g_switch_out_ep_fail_count = 0;
static volatile uint32_t g_switch_out_sent_count = 0;
static volatile uint32_t g_switch_out_ctrl_submit_count = 0;
static volatile uint32_t g_switch_out_ctrl_done_count = 0;
static volatile uint32_t g_switch_out_ctrl_fail_count = 0;
static volatile uint32_t g_switch_out_complete_timeout_count = 0;
static volatile uint64_t g_switch_next_init_us = 0;
static volatile uint64_t g_switch_wait_deadline_us = 0;
static volatile uint64_t g_switch_output_deadline_us = 0;

static critical_section_t g_latest_report_lock;
static critical_section_t g_mapper_input_lock;
static uint8_t g_latest_report[DEBUG_MAX_REPORT_LEN];
static uint16_t g_latest_report_len = 0;
static uint32_t g_latest_report_seq = 0;
static uint64_t g_latest_report_time_us = 0;
static uint8_t g_latest_report_dev_addr = 0;
static uint8_t g_latest_report_instance = 0;

static char g_cdc_command[CDC_COMMAND_MAX_LEN];
static uint8_t g_cdc_command_len = 0;

static bool g_capture_active = false;
static char g_capture_label[CDC_COMMAND_MAX_LEN];
static uint8_t g_capture_sample_index = 0;
static uint64_t g_capture_next_sample_us = 0;

static volatile bool g_host_rescan_requested = false;
static volatile uint32_t g_host_rescan_count = 0;
static volatile uint64_t g_host_next_auto_rescan_us = 0;

// ============================================================
// Debug print helpers
// ============================================================

static float clamp_float(float v, float lo, float hi);
static void clear_gamepad_state(void);
static bool gamepad_input_is_fresh(gamepad_freshness_snapshot_t *snapshot_out);
static void reset_switch_init_state(void);

#if !PICO_FIRMWARE_MAPPER || MAPPER_ENABLE_CDC_STATUS || \
    DEBUG_PRINT_RAW_REPORTS || MAPPER_TRACE_MOUSE_OUTPUT
static void cdc_write_string(char const *s) {
    if (!tud_cdc_connected()) {
        return;
    }

    size_t len = strlen(s);
    size_t offset = 0;

    while (offset < len) {
        uint32_t written = tud_cdc_write(s + offset, len - offset);

        if (written == 0) {
            break;
        }

        offset += written;
    }

    tud_cdc_write_flush();
}

static void cdc_printf_raw(char const *s) {
    cdc_write_string(s);
}
#else
static void cdc_printf_raw(char const *s) {
    (void)s;
}
#endif

static void record_latest_report(
    uint8_t dev_addr,
    uint8_t instance,
    uint8_t const *report,
    uint16_t len
) {
    uint16_t copy_len = len;

    if (copy_len > DEBUG_MAX_REPORT_LEN) {
        copy_len = DEBUG_MAX_REPORT_LEN;
    }

    critical_section_enter_blocking(&g_latest_report_lock);

    memcpy(g_latest_report, report, copy_len);
    g_latest_report_len = copy_len;
    g_latest_report_seq++;
    g_latest_report_time_us = time_us_64();
    g_latest_report_dev_addr = dev_addr;
    g_latest_report_instance = instance;

    critical_section_exit(&g_latest_report_lock);
}

static bool snapshot_latest_report(
    uint8_t *report,
    uint16_t *len,
    uint32_t *seq,
    uint64_t *report_time_us,
    uint8_t *dev_addr,
    uint8_t *instance
) {
    critical_section_enter_blocking(&g_latest_report_lock);

    bool has_report = g_latest_report_len > 0;

    if (has_report) {
        *len = g_latest_report_len;
        *seq = g_latest_report_seq;
        *report_time_us = g_latest_report_time_us;
        *dev_addr = g_latest_report_dev_addr;
        *instance = g_latest_report_instance;
        memcpy(report, g_latest_report, g_latest_report_len);
    }

    critical_section_exit(&g_latest_report_lock);

    return has_report;
}

static bool host_root_line_has_device(root_port_t *root) {
    port_pin_status_t line_state = pio_usb_bus_get_line_state(root);
    return line_state == PORT_PIN_FS_IDLE || line_state == PORT_PIN_LS_IDLE;
}

static void request_host_rescan(void) {
    g_host_rescan_requested = true;
}

static void host_rescan_task(void) {
    root_port_t *root = PIO_USB_ROOT_PORT(0);
    uint64_t now_us = time_us_64();
    bool should_rescan = g_host_rescan_requested;

    if (!g_host_device_mounted &&
        root->initialized &&
        root->connected &&
        host_root_line_has_device(root) &&
        now_us >= g_host_next_auto_rescan_us) {
        should_rescan = true;
    }

    if (!should_rescan) {
        return;
    }

    g_host_rescan_requested = false;
    g_host_next_auto_rescan_us = now_us + HOST_AUTO_RESCAN_INTERVAL_US;
    g_host_rescan_count++;

    root->ints = 0;
    root->connected = false;
    root->suspended = true;
    clear_gamepad_state();
    reset_switch_init_state();
}

static void debug_print_hex_report(uint8_t const *report, uint16_t len) {
#if DEBUG_PRINT_RAW_REPORTS
    if (!tud_cdc_connected()) {
        return;
    }

#if DEBUG_PRINT_ONLY_CHANGED_REPORTS
    if (g_has_last_report && len == g_last_report_len && memcmp(g_last_report, report, len) == 0) {
        return;
    }
#endif

    uint16_t copy_len = len;

    if (copy_len > DEBUG_MAX_REPORT_LEN) {
        copy_len = DEBUG_MAX_REPORT_LEN;
    }

    memcpy(g_last_report, report, copy_len);
    g_last_report_len = copy_len;
    g_has_last_report = true;

    g_report_count++;

    char line[256];
    int pos = 0;

    pos += snprintf(
        line + pos,
        sizeof(line) - pos,
        "REPORT #%lu len=%u : ",
        (unsigned long)g_report_count,
        len
    );

    for (uint16_t i = 0; i < len && pos < (int)sizeof(line) - 4; i++) {
        pos += snprintf(line + pos, sizeof(line) - pos, "%02X ", report[i]);
    }

    pos += snprintf(line + pos, sizeof(line) - pos, "\r\n");

    tud_cdc_write(line, strlen(line));
    tud_cdc_write_flush();
#else
    (void)report;
    (void)len;
#endif
}

static char const *hid_protocol_name(uint8_t protocol) {
    switch (protocol) {
        case HID_ITF_PROTOCOL_KEYBOARD:
            return "keyboard";

        case HID_ITF_PROTOCOL_MOUSE:
            return "mouse";

        default:
            return "none/gamepad";
    }
}

static char const *line_state_name(port_pin_status_t line_state) {
    switch (line_state) {
        case PORT_PIN_SE0:
            return "SE0";

        case PORT_PIN_FS_IDLE:
            return "FS_IDLE";

        case PORT_PIN_LS_IDLE:
            return "LS_IDLE";

        case PORT_PIN_SE1:
            return "SE1";

        default:
            return "?";
    }
}

static bool is_switch_pro_controller(uint16_t vid, uint16_t pid) {
    return vid == NINTENDO_VID && pid == NINTENDO_SWITCH_PRO_PID;
}

static bool report_is_from_active_hid(uint8_t dev_addr, uint8_t instance) {
    return g_host_hid_mounted &&
           dev_addr == g_host_dev_addr &&
           instance == g_host_hid_instance;
}

static void reset_switch_init_state(void) {
    g_switch_init_step = SWITCH_INIT_IDLE;
    g_switch_init_retry_count = 0;
    g_switch_wait_ack_kind = SWITCH_ACK_NONE;
    g_switch_wait_ack_id = 0;
    g_switch_output_pending = false;
    g_switch_next_init_us = 0;
    g_switch_wait_deadline_us = 0;
    g_switch_output_deadline_us = 0;
}

static void begin_switch_init(void) {
    g_switch_centered = false;
    g_switch_init_step = SWITCH_INIT_USB_HANDSHAKE_1;
    g_switch_init_retry_count = 0;
    g_switch_subcmd_packet = 0;
    g_switch_wait_ack_kind = SWITCH_ACK_NONE;
    g_switch_wait_ack_id = 0;
    g_switch_output_pending = false;
    g_switch_next_init_us = time_us_64() + 50000u;
    g_switch_wait_deadline_us = 0;
    g_switch_output_deadline_us = 0;
}

static void clear_gamepad_state(void) {
    critical_section_enter_blocking(&g_mapper_input_lock);

    g_lx = 0.0f;
    g_ly = 0.0f;
    g_rx = 0.0f;
    g_ry = 0.0f;

    g_lt_analog = 0.0f;
    g_rt_analog = 0.0f;
    g_dpad = 0x0F;

    g_a = false;
    g_b = false;
    g_x = false;
    g_y = false;
    g_r5 = false;
    g_lb = false;
    g_rb = false;
    g_lt_digital = false;
    g_rt_digital = false;
    g_setting = false;
    g_menu = false;
    g_l3 = false;
    g_r3 = false;

    g_switch_buttons = 0;
    g_switch_raw_lx = 2048;
    g_switch_raw_ly = 2048;
    g_switch_raw_rx = 2048;
    g_switch_raw_ry = 2048;

    g_gamepad_valid = false;
    g_last_valid_report_us = 0;

    critical_section_exit(&g_mapper_input_lock);
}

static uint16_t switch_stick_x(uint8_t const *stick) {
    return (uint16_t)(stick[0] | ((stick[1] & 0x0F) << 8));
}

static uint16_t switch_stick_y(uint8_t const *stick) {
    return (uint16_t)((stick[1] >> 4) | (stick[2] << 4));
}

static float normalize_switch_axis(uint16_t raw, uint16_t center) {
    int32_t delta = (int32_t)raw - (int32_t)center;
    int32_t range = delta >= 0 ? (4095 - (int32_t)center) : (int32_t)center;

    if (range <= 0) {
        return 0.0f;
    }

    return clamp_float((float)delta / (float)range, -1.0f, 1.0f);
}

// ============================================================
// Helper functions
// ============================================================

static float clamp_float(float v, float lo, float hi) {
    if (v < lo) {
        return lo;
    }

    if (v > hi) {
        return hi;
    }

    return v;
}

static int clamp_int(int v, int lo, int hi) {
    if (v < lo) {
        return lo;
    }

    if (v > hi) {
        return hi;
    }

    return v;
}

static float normalize_u8_axis(uint8_t v) {
    float x = ((float)v - 128.0f) / 127.0f;
    return clamp_float(x, -1.0f, 1.0f);
}

static uint16_t scale_u8_to_u12(uint8_t v) {
    return (uint16_t)(((uint32_t)v * 4095u + 127u) / 255u);
}

static float apply_deadzone(float v, float dz) {
    float a = fabsf(v);

    if (a < dz) {
        return 0.0f;
    }

    float sign = v >= 0.0f ? 1.0f : -1.0f;
    return sign * ((a - dz) / (1.0f - dz));
}

static uint8_t dpad_to_wasd(uint8_t dpad) {
    switch (dpad & DPAD_MASK) {
        case 0x00:
            return KEY_MASK_W;

        case 0x01:
            return KEY_MASK_W | KEY_MASK_D;

        case 0x02:
            return KEY_MASK_D;

        case 0x03:
            return KEY_MASK_S | KEY_MASK_D;

        case 0x04:
            return KEY_MASK_S;

        case 0x05:
            return KEY_MASK_S | KEY_MASK_A;

        case 0x06:
            return KEY_MASK_A;

        case 0x07:
            return KEY_MASK_W | KEY_MASK_A;

        case 0x0F:
        default:
            return 0;
    }
}

static uint8_t left_stick_to_wasd(float lx, float ly) {
    float mag = sqrtf(lx * lx + ly * ly);

    if (mag < LEFT_DEADZONE) {
        return 0;
    }

    float angle = atan2f(ly, lx) * 180.0f / 3.14159265f;

    if (angle < 0.0f) {
        angle += 360.0f;
    }

    if (angle >= 247.5f && angle < 292.5f) {
        return KEY_MASK_W;
    }

    if (angle >= 292.5f && angle < 337.5f) {
        return KEY_MASK_W | KEY_MASK_D;
    }

    if (angle >= 337.5f || angle < 22.5f) {
        return KEY_MASK_D;
    }

    if (angle >= 22.5f && angle < 67.5f) {
        return KEY_MASK_S | KEY_MASK_D;
    }

    if (angle >= 67.5f && angle < 112.5f) {
        return KEY_MASK_S;
    }

    if (angle >= 112.5f && angle < 157.5f) {
        return KEY_MASK_S | KEY_MASK_A;
    }

    if (angle >= 157.5f && angle < 202.5f) {
        return KEY_MASK_A;
    }

    if (angle >= 202.5f && angle < 247.5f) {
        return KEY_MASK_W | KEY_MASK_A;
    }

    return 0;
}

static uint8_t left_stick_to_4way_wasd(float lx, float ly) {
    float mag = sqrtf(lx * lx + ly * ly);

    if (mag < LEFT_DEADZONE) {
        return 0;
    }

    if (fabsf(lx) >= fabsf(ly)) {
        return lx < 0.0f ? KEY_MASK_A : KEY_MASK_D;
    }

    return ly < 0.0f ? KEY_MASK_W : KEY_MASK_S;
}

// ============================================================
// HID output
// ============================================================

static bool hid_any_ready(void) {
    return tud_hid_n_ready(HID_INSTANCE_KEYBOARD) ||
           tud_hid_n_ready(HID_INSTANCE_MOUSE);
}

static bool send_keyboard_mask(uint8_t key_mask) {
    uint8_t keycode[6] = {0, 0, 0, 0, 0, 0};
    uint8_t index = 0;

    if ((key_mask & KEY_MASK_W) && index < 6) {
        keycode[index++] = HID_KEY_W;
    }

    if ((key_mask & KEY_MASK_A) && index < 6) {
        keycode[index++] = HID_KEY_A;
    }

    if ((key_mask & KEY_MASK_S) && index < 6) {
        keycode[index++] = HID_KEY_S;
    }

    if ((key_mask & KEY_MASK_D) && index < 6) {
        keycode[index++] = HID_KEY_D;
    }

    return tud_hid_n_keyboard_report(HID_INSTANCE_KEYBOARD, 0, 0, keycode);
}

static bool keycodes_match(uint8_t const *a, uint8_t const *b) {
    for (uint8_t i = 0; i < 6; i++) {
        if (a[i] != b[i]) {
            return false;
        }
    }

    return true;
}

static void add_keycode(uint8_t keycode[6], uint8_t *count, uint8_t key) {
    if (key == 0) {
        return;
    }

    for (uint8_t i = 0; i < *count; i++) {
        if (keycode[i] == key) {
            return;
        }
    }

    if (*count < 6) {
        keycode[*count] = key;
        (*count)++;
    }
}

static void reset_hold_action(hold_action_t *action) {
    action->pressed = false;
    action->hold_active = false;
    action->press_time_us = 0;
    action->tap_until_us = 0;
}

static void reset_click_action(click_action_t *action) {
    action->pressed = false;
    action->waiting_single = false;
    action->double_active = false;
    action->single_deadline_us = 0;
    action->tap_until_us = 0;
    action->tap_key = 0;
}

static void reset_double_hold_action(double_hold_action_t *action) {
    action->pressed = false;
    action->hold_active = false;
    action->waiting_double = false;
    action->double_active = false;
    action->press_time_us = 0;
    action->double_deadline_us = 0;
    action->tap_until_us = 0;
}

static void reset_snapshot_macro(void) {
    g_snapshot_button_pressed = false;
    g_snapshot_macro_active = false;
    g_snapshot_macro_start_us = 0;
}

static void reset_mapper_actions(void) {
    reset_hold_action(&g_hold_dpad_up);
    reset_hold_action(&g_hold_dpad_down);
    reset_hold_action(&g_hold_x);
    reset_hold_action(&g_hold_b);
    reset_hold_action(&g_hold_option);
    reset_hold_action(&g_hold_rstick);
    reset_hold_action(&g_hold_a_wheel);
    reset_click_action(&g_click_x);
    reset_double_hold_action(&g_dpad_down_wheel);
    g_rstick_pending_tap_key = 0;
    g_pending_wheel = 0;
    g_wheel_up_next_us = 0;
    g_wheel_down_next_us = 0;
    g_combo_wheel_up_next_us = 0;
    g_combo_wheel_down_next_us = 0;
    g_mouse_left_release_deadline_us = 0;
    g_mouse_right_release_deadline_us = 0;
    reset_snapshot_macro();
    g_profile2_outer_active = false;
    g_profile2_outer_rb = false;
    g_profile2_outer_start_us = 0;
}

static void mapper_request_output_release(void) {
    mapper_action_request_release();

    reset_mapper_actions();
    g_mapper_release_pending = true;
}

static void update_snapshot_macro(uint32_t buttons, uint64_t now_us) {
    bool is_pressed = (buttons & SW_BTN_SNAPSHOT) != 0;

    if (g_snapshot_macro_active &&
        now_us - g_snapshot_macro_start_us >= SNAPSHOT_TOTAL_US) {
        g_snapshot_macro_active = false;
        g_snapshot_macro_start_us = 0;
    }

    if (is_pressed && !g_snapshot_button_pressed) {
        g_snapshot_button_pressed = true;
        return;
    }

    if (is_pressed) {
        return;
    }

    if (g_snapshot_button_pressed) {
        g_snapshot_macro_active = true;
        g_snapshot_macro_start_us = now_us;
        g_snapshot_button_pressed = false;
    }
}

static bool snapshot_macro_alt_down(uint64_t now_us) {
    return g_snapshot_macro_active &&
           now_us - g_snapshot_macro_start_us < SNAPSHOT_TOTAL_US;
}

static bool snapshot_macro_right_down(uint64_t now_us) {
    if (!g_snapshot_macro_active) {
        return false;
    }

    uint64_t elapsed_us = now_us - g_snapshot_macro_start_us;
    return elapsed_us >= SNAPSHOT_ALT_TO_RIGHT_DOWN_US &&
           elapsed_us < SNAPSHOT_RIGHT_UP_US;
}

static void add_hold_or_tap_key(
    hold_action_t *action,
    bool is_pressed,
    uint8_t tap_key,
    uint8_t hold_key,
    uint64_t now_us,
    uint8_t keycode[6],
    uint8_t *count
) {
    if (is_pressed && !action->pressed) {
        action->pressed = true;
        action->hold_active = false;
        action->press_time_us = now_us;
    }

    if (is_pressed &&
        !action->hold_active &&
        now_us - action->press_time_us >= HOLD_THRESHOLD_US) {
        action->hold_active = true;
    }

    if (!is_pressed && action->pressed) {
        if (!action->hold_active) {
            action->tap_until_us = now_us + TAP_OUTPUT_US;
        }

        action->pressed = false;
        action->hold_active = false;
        action->press_time_us = 0;
    }

    if (is_pressed && action->hold_active) {
        add_keycode(keycode, count, hold_key);
    }

    if (action->tap_until_us != 0) {
        if (now_us < action->tap_until_us) {
            add_keycode(keycode, count, tap_key);
        } else {
            action->tap_until_us = 0;
        }
    }
}

static void add_wheel_if_due(
    bool active,
    int8_t wheel_delta,
    uint64_t now_us,
    uint64_t *next_wheel_us,
    uint64_t interval_us
) {
    if (!active) {
        *next_wheel_us = 0;
        return;
    }

    if (*next_wheel_us == 0 || now_us >= *next_wheel_us) {
        int32_t next_wheel = (int32_t)g_pending_wheel + wheel_delta;
        g_pending_wheel = (int16_t)clamp_int(next_wheel, -127, 127);
        *next_wheel_us = now_us + interval_us;
    }
}

static void add_turbo_wheel_if_due(
    bool active,
    int8_t wheel_delta,
    uint64_t now_us,
    uint64_t *next_wheel_us
) {
    add_wheel_if_due(active, wheel_delta, now_us, next_wheel_us, TURBO_30HZ_INTERVAL_US);
}

static void add_tap_or_hold_wheel(
    hold_action_t *action,
    bool is_pressed,
    uint8_t tap_key,
    int8_t wheel_delta,
    uint64_t now_us,
    uint8_t keycode[6],
    uint8_t *count,
    uint64_t *next_wheel_us
) {
    if (is_pressed && !action->pressed) {
        action->pressed = true;
        action->hold_active = false;
        action->press_time_us = now_us;
    }

    if (is_pressed &&
        !action->hold_active &&
        now_us - action->press_time_us >= HOLD_THRESHOLD_US) {
        action->hold_active = true;
    }

    if (!is_pressed && action->pressed) {
        if (!action->hold_active) {
            action->tap_until_us = now_us + TAP_OUTPUT_US;
        }

        action->pressed = false;
        action->hold_active = false;
        action->press_time_us = 0;
    }

    add_turbo_wheel_if_due(is_pressed && action->hold_active, wheel_delta, now_us, next_wheel_us);

    if (action->tap_until_us != 0) {
        if (now_us < action->tap_until_us) {
            add_keycode(keycode, count, tap_key);
        } else {
            action->tap_until_us = 0;
        }
    }
}

static void add_single_double_key(
    click_action_t *action,
    bool is_pressed,
    uint8_t single_key,
    uint8_t double_key,
    uint64_t now_us,
    uint8_t keycode[6],
    uint8_t *count
) {
    if (action->waiting_single && now_us >= action->single_deadline_us) {
        action->waiting_single = false;
        action->tap_key = single_key;
        action->tap_until_us = now_us + TAP_OUTPUT_US;
    }

    if (is_pressed && !action->pressed) {
        action->pressed = true;

        if (action->waiting_single && now_us < action->single_deadline_us) {
            action->waiting_single = false;
            action->double_active = true;
            action->tap_key = double_key;
            action->tap_until_us = now_us + TAP_OUTPUT_US;
        } else {
            action->double_active = false;
        }
    }

    if (!is_pressed && action->pressed) {
        if (!action->double_active) {
            action->waiting_single = true;
            action->single_deadline_us = now_us + DOUBLE_CLICK_US;
        }

        action->pressed = false;
        action->double_active = false;
    }

    if (action->tap_until_us != 0) {
        if (now_us < action->tap_until_us) {
            add_keycode(keycode, count, action->tap_key);
        } else {
            action->tap_until_us = 0;
            action->tap_key = 0;
        }
    }
}

static void add_double_or_hold_wheel(
    double_hold_action_t *action,
    bool is_pressed,
    uint8_t double_key,
    int8_t wheel_delta,
    uint64_t now_us,
    uint8_t keycode[6],
    uint8_t *count,
    uint64_t *next_wheel_us
) {
    if (action->waiting_double && now_us >= action->double_deadline_us) {
        action->waiting_double = false;
    }

    if (is_pressed && !action->pressed) {
        action->pressed = true;
        action->hold_active = false;
        action->press_time_us = now_us;

        if (action->waiting_double && now_us < action->double_deadline_us) {
            action->waiting_double = false;
            action->double_active = true;
            action->tap_until_us = now_us + TAP_OUTPUT_US;
        } else {
            action->double_active = false;
        }
    }

    if (is_pressed &&
        !action->double_active &&
        !action->hold_active &&
        now_us - action->press_time_us >= HOLD_THRESHOLD_US) {
        action->hold_active = true;
        action->waiting_double = false;
    }

    if (!is_pressed && action->pressed) {
        if (!action->hold_active && !action->double_active) {
            action->waiting_double = true;
            action->double_deadline_us = now_us + DOUBLE_CLICK_US;
        }

        action->pressed = false;
        action->hold_active = false;
        action->double_active = false;
        action->press_time_us = 0;
    }

    add_turbo_wheel_if_due(is_pressed && action->hold_active, wheel_delta, now_us, next_wheel_us);

    if (action->tap_until_us != 0) {
        if (now_us < action->tap_until_us) {
            add_keycode(keycode, count, double_key);
        } else {
            action->tap_until_us = 0;
        }
    }
}

static void add_rstick_hold_or_alternating_tap_key(
    bool is_pressed,
    uint8_t hold_key,
    uint64_t now_us,
    uint8_t keycode[6],
    uint8_t *count
) {
    if (is_pressed && !g_hold_rstick.pressed) {
        g_hold_rstick.pressed = true;
        g_hold_rstick.hold_active = false;
        g_hold_rstick.press_time_us = now_us;
    }

    if (is_pressed &&
        !g_hold_rstick.hold_active &&
        now_us - g_hold_rstick.press_time_us >= HOLD_THRESHOLD_US) {
        g_hold_rstick.hold_active = true;
    }

    if (!is_pressed && g_hold_rstick.pressed) {
        if (!g_hold_rstick.hold_active) {
            g_rstick_pending_tap_key = g_rstick_next_tap_is_1 ? HID_KEY_1 : HID_KEY_2;
            g_rstick_next_tap_is_1 = !g_rstick_next_tap_is_1;
            g_hold_rstick.tap_until_us = now_us + TAP_OUTPUT_US;
        }

        g_hold_rstick.pressed = false;
        g_hold_rstick.hold_active = false;
        g_hold_rstick.press_time_us = 0;
    }

    if (is_pressed && g_hold_rstick.hold_active) {
        add_keycode(keycode, count, hold_key);
    }

    if (g_hold_rstick.tap_until_us != 0) {
        if (now_us < g_hold_rstick.tap_until_us && g_rstick_pending_tap_key != 0) {
            add_keycode(keycode, count, g_rstick_pending_tap_key);
        } else {
            g_hold_rstick.tap_until_us = 0;
            g_rstick_pending_tap_key = 0;
        }
    }
}

static uint8_t build_mapper_keycodes(uint8_t keycode[6], uint64_t now_us) {
#if PICO_FIRMWARE_MAPPER
    return mapper_action_build_keycodes(keycode, now_us);
    (void)now_us;
#endif

    uint8_t count = 0;
    uint32_t buttons = g_switch_buttons;
    uint8_t modifier = 0;
    update_snapshot_macro(buttons, now_us);

    bool combo_held = (buttons & SW_BTN_LT) && (buttons & SW_BTN_RT);
    bool combo_x = combo_held && (buttons & SW_BTN_X);
    bool combo_y = combo_held && (buttons & SW_BTN_Y);
    bool combo_a = combo_held && (buttons & SW_BTN_A);
    bool combo_b = combo_held && (buttons & SW_BTN_B);
    bool combo_dpad_left = combo_held && (buttons & SW_BTN_DPAD_LEFT);
    bool combo_dpad_right = combo_held && (buttons & SW_BTN_DPAD_RIGHT);
    bool face_combo_active = combo_x || combo_y || combo_a || combo_b;
    bool combo_wheel_up = combo_held && (buttons & SW_BTN_DPAD_UP);
    bool combo_wheel_down = combo_held && (buttons & SW_BTN_DPAD_DOWN);
    bool wheel_combo_active = combo_wheel_up || combo_wheel_down;
    bool p1_dpad_left_f4_combo = g_mapper_profile == MAPPER_PROFILE_1 &&
                                  combo_dpad_left;
    bool p1_dpad_right_h_combo = g_mapper_profile == MAPPER_PROFILE_1 &&
                                  combo_dpad_right;
    bool p1_dpad_combo_active = p1_dpad_left_f4_combo ||
                                p1_dpad_right_h_combo;
    bool p2_lstick_y_combo = g_mapper_profile == MAPPER_PROFILE_2 &&
                              (buttons & SW_BTN_LSTICK) &&
                              (buttons & SW_BTN_Y);
    bool p2_lb_b_combo = g_mapper_profile == MAPPER_PROFILE_2 &&
                          (buttons & SW_BTN_LB) &&
                          (buttons & SW_BTN_B);
    bool p2_lb_dpad_down_combo = g_mapper_profile == MAPPER_PROFILE_2 &&
                                  !combo_wheel_down &&
                                  (buttons & SW_BTN_LB) &&
                                  (buttons & SW_BTN_DPAD_DOWN);
    bool p3_lt_rt_combo = g_mapper_profile == MAPPER_PROFILE_3 &&
                           !wheel_combo_active &&
                           (buttons & SW_BTN_LT) &&
                           (buttons & SW_BTN_RT);
    bool p3_lb_b_combo = g_mapper_profile == MAPPER_PROFILE_3 &&
                          (buttons & SW_BTN_LB) &&
                          (buttons & SW_BTN_B);

    add_wheel_if_due(
        combo_wheel_up,
        1,
        now_us,
        &g_combo_wheel_up_next_us,
        COMBO_10HZ_INTERVAL_US
    );
    add_wheel_if_due(
        combo_wheel_down,
        -1,
        now_us,
        &g_combo_wheel_down_next_us,
        COMBO_10HZ_INTERVAL_US
    );

    uint8_t wasd_mask = g_mapper_profile == MAPPER_PROFILE_2 ?
                         left_stick_to_4way_wasd(g_lx, g_ly) :
                         left_stick_to_wasd(g_lx, g_ly);

    if (wasd_mask & KEY_MASK_W) {
        add_keycode(keycode, &count, HID_KEY_W);
    }

    if (wasd_mask & KEY_MASK_A) {
        add_keycode(keycode, &count, HID_KEY_A);
    }

    if (wasd_mask & KEY_MASK_S) {
        add_keycode(keycode, &count, HID_KEY_S);
    }

    if (wasd_mask & KEY_MASK_D) {
        add_keycode(keycode, &count, HID_KEY_D);
    }

    if ((buttons & SW_BTN_DPAD_LEFT) && !p1_dpad_left_f4_combo) {
        add_keycode(keycode, &count, HID_KEY_B);
    }

    switch (g_mapper_profile) {
        case MAPPER_PROFILE_2:
            if (combo_wheel_up) {
                reset_hold_action(&g_hold_dpad_up);
            } else if (buttons & SW_BTN_DPAD_UP) {
                add_keycode(keycode, &count, HID_KEY_G);
                reset_hold_action(&g_hold_dpad_up);
            }

            if (buttons & SW_BTN_DPAD_RIGHT) {
                add_keycode(keycode, &count, HID_KEY_4);
            }

            reset_double_hold_action(&g_dpad_down_wheel);
            if (p2_lb_dpad_down_combo) {
                add_keycode(keycode, &count, HID_KEY_H);
                add_turbo_wheel_if_due(false, 1, now_us, &g_wheel_up_next_us);
            } else if (combo_wheel_down) {
                add_turbo_wheel_if_due(false, 1, now_us, &g_wheel_up_next_us);
            } else {
                add_turbo_wheel_if_due(
                    (buttons & SW_BTN_DPAD_DOWN) != 0,
                    1,
                    now_us,
                    &g_wheel_up_next_us
                );
            }
            reset_hold_action(&g_hold_dpad_down);
            break;

        case MAPPER_PROFILE_3:
            if (combo_wheel_up) {
                reset_hold_action(&g_hold_dpad_up);
            } else if (buttons & SW_BTN_DPAD_UP) {
                add_keycode(keycode, &count, HID_KEY_L);
                reset_hold_action(&g_hold_dpad_up);
            }

            if (buttons & SW_BTN_DPAD_RIGHT) {
                add_keycode(keycode, &count, HID_KEY_5);
            }

            if ((buttons & SW_BTN_DPAD_DOWN) && !combo_wheel_down) {
                add_keycode(keycode, &count, HID_KEY_H);
            }

            reset_hold_action(&g_hold_dpad_down);
            break;

        case MAPPER_PROFILE_1:
        default:
            if (p1_dpad_left_f4_combo) {
                add_keycode(keycode, &count, HID_KEY_F4);
            }

            if (p1_dpad_right_h_combo) {
                add_keycode(keycode, &count, HID_KEY_H);
            } else if (buttons & SW_BTN_DPAD_RIGHT) {
                add_keycode(keycode, &count, HID_KEY_GRAVE);
            }

            if (combo_wheel_up) {
                reset_hold_action(&g_hold_dpad_up);
            } else {
                add_hold_or_tap_key(
                    &g_hold_dpad_up,
                    (buttons & SW_BTN_DPAD_UP) != 0,
                    HID_KEY_5,
                    HID_KEY_G,
                    now_us,
                    keycode,
                    &count
                );
            }

            if (combo_wheel_down) {
                reset_hold_action(&g_hold_dpad_down);
            } else {
                add_hold_or_tap_key(
                    &g_hold_dpad_down,
                    (buttons & SW_BTN_DPAD_DOWN) != 0,
                    HID_KEY_3,
                    HID_KEY_4,
                    now_us,
                    keycode,
                    &count
                );
            }
            break;
    }

    if (p2_lstick_y_combo) {
        add_keycode(keycode, &count, HID_KEY_Z);
    } else if ((buttons & SW_BTN_LSTICK) != 0) {
        if (g_mapper_profile == MAPPER_PROFILE_2) {
            add_keycode(keycode, &count, HID_KEY_Q);
        } else {
            modifier |= KEYBOARD_MODIFIER_LEFTSHIFT;
        }
    }

    if (g_mapper_profile != MAPPER_PROFILE_3 && face_combo_active) {
        modifier |= KEYBOARD_MODIFIER_LEFTCTRL;

        if (combo_x) {
            add_keycode(keycode, &count, HID_KEY_1);
            reset_click_action(&g_click_x);
            reset_hold_action(&g_hold_x);
        }

        if (combo_y) {
            add_keycode(keycode, &count, HID_KEY_2);
        }

        if (combo_a) {
            add_keycode(keycode, &count, HID_KEY_3);
        }

        if (combo_b) {
            add_keycode(keycode, &count, HID_KEY_4);
            reset_hold_action(&g_hold_b);
        }
    }

    switch (g_mapper_profile) {
        case MAPPER_PROFILE_2:
            if ((buttons & SW_BTN_LT) && !face_combo_active && !wheel_combo_active) {
                modifier |= KEYBOARD_MODIFIER_LEFTCTRL;
            }

            if ((buttons & SW_BTN_RT) && !face_combo_active && !wheel_combo_active) {
                add_keycode(keycode, &count, HID_KEY_SPACE);
            }

            if ((buttons & SW_BTN_A) && !combo_a) {
                add_keycode(keycode, &count, HID_KEY_V);
            }

            reset_hold_action(&g_hold_a_wheel);
            break;

        case MAPPER_PROFILE_3:
            if (p3_lt_rt_combo) {
                add_keycode(keycode, &count, HID_KEY_X);
            } else {
                if ((buttons & SW_BTN_LT) && !wheel_combo_active) {
                    add_keycode(
                        keycode,
                        &count,
                        (buttons & SW_BTN_LB) ? HID_KEY_Q : HID_KEY_V
                    );
                }

                if ((buttons & SW_BTN_RT) && !wheel_combo_active) {
                    add_keycode(
                        keycode,
                        &count,
                        (buttons & SW_BTN_LB) ? HID_KEY_E : HID_KEY_G
                    );
                }
            }

            if ((buttons & SW_BTN_A) != 0) {
                add_keycode(keycode, &count, HID_KEY_SPACE);
            }

            reset_hold_action(&g_hold_a_wheel);
            g_wheel_down_next_us = 0;
            break;

        case MAPPER_PROFILE_1:
        default:
            if ((buttons & SW_BTN_LT) &&
                !face_combo_active &&
                !wheel_combo_active &&
                !p1_dpad_combo_active) {
                add_keycode(keycode, &count, HID_KEY_Q);
            }

            if ((buttons & SW_BTN_RT) &&
                !face_combo_active &&
                !wheel_combo_active &&
                !p1_dpad_combo_active) {
                add_keycode(keycode, &count, HID_KEY_E);
            }

            if ((buttons & SW_BTN_A) && !combo_a) {
                add_keycode(keycode, &count, HID_KEY_SPACE);
            }

            reset_hold_action(&g_hold_a_wheel);
            g_wheel_down_next_us = 0;
            break;
    }

    if (buttons & SW_BTN_MENU) {
        add_keycode(keycode, &count, HID_KEY_TAB);
    }

    if (snapshot_macro_alt_down(now_us)) {
        modifier |= KEYBOARD_MODIFIER_LEFTALT;
    }

    if (p2_lb_b_combo) {
        modifier |= KEYBOARD_MODIFIER_LEFTSHIFT;
        reset_hold_action(&g_hold_b);
        add_turbo_wheel_if_due(false, -1, now_us, &g_wheel_down_next_us);
    } else if (g_mapper_profile == MAPPER_PROFILE_2) {
        reset_hold_action(&g_hold_b);
        add_turbo_wheel_if_due(
            (buttons & SW_BTN_B) != 0 && !combo_b,
            -1,
            now_us,
            &g_wheel_down_next_us
        );
    } else if (p3_lb_b_combo) {
        add_keycode(keycode, &count, HID_KEY_U);
        reset_hold_action(&g_hold_b);
    } else {
        add_hold_or_tap_key(
            &g_hold_b,
            (buttons & SW_BTN_B) != 0 && !combo_b,
            HID_KEY_C,
            HID_KEY_Z,
            now_us,
            keycode,
            &count
        );
    }

    if (g_mapper_profile == MAPPER_PROFILE_1) {
        add_hold_or_tap_key(
            &g_hold_x,
            (buttons & SW_BTN_X) != 0 && !combo_x,
            HID_KEY_R,
            HID_KEY_F,
            now_us,
            keycode,
            &count
        );
        reset_click_action(&g_click_x);
    } else if (g_mapper_profile == MAPPER_PROFILE_2) {
        add_hold_or_tap_key(
            &g_hold_x,
            (buttons & SW_BTN_X) != 0 && !combo_x,
            HID_KEY_R,
            HID_KEY_E,
            now_us,
            keycode,
            &count
        );
        reset_click_action(&g_click_x);
    } else if (!combo_x && !p3_lt_rt_combo) {
        reset_hold_action(&g_hold_x);
        add_single_double_key(
            &g_click_x,
            (buttons & SW_BTN_X) != 0,
            HID_KEY_R,
            HID_KEY_F,
            now_us,
            keycode,
            &count
        );
    } else {
        reset_hold_action(&g_hold_x);
        reset_click_action(&g_click_x);
    }

    add_hold_or_tap_key(
        &g_hold_option,
        (buttons & SW_BTN_OPTION) != 0,
        g_mapper_profile == MAPPER_PROFILE_2 ? HID_KEY_ESCAPE : HID_KEY_M,
        g_mapper_profile == MAPPER_PROFILE_2 ? HID_KEY_M : HID_KEY_ESCAPE,
        now_us,
        keycode,
        &count
    );

    add_rstick_hold_or_alternating_tap_key(
        (buttons & SW_BTN_RSTICK) != 0,
        g_mapper_profile == MAPPER_PROFILE_2 ? HID_KEY_3 : HID_KEY_X,
        now_us,
        keycode,
        &count
    );

    return modifier;
}

static bool send_keyboard_keycodes_if_changed(uint8_t modifier, uint8_t const keycode[6]) {
    if (modifier == g_last_modifier && keycodes_match(keycode, g_last_keycode)) {
        return false;
    }

    if (!tud_hid_n_keyboard_report(HID_INSTANCE_KEYBOARD, 0, modifier, keycode)) {
        return false;
    }

    g_last_modifier = modifier;
    memcpy(g_last_keycode, keycode, sizeof(g_last_keycode));

    return true;
}

static bool send_keyboard_neutral_if_needed(void) {
    uint8_t keycode[6] = {0, 0, 0, 0, 0, 0};

    return send_keyboard_keycodes_if_changed(0, keycode);
}

static bool mouse_button_down_with_grace(
    bool raw_pressed,
    uint64_t now_us,
    uint64_t *release_deadline_us
) {
    if (raw_pressed) {
        *release_deadline_us = now_us + MOUSE_BUTTON_RELEASE_GRACE_US;
        return true;
    }

    if (*release_deadline_us != 0 && now_us < *release_deadline_us) {
        return true;
    }

    *release_deadline_us = 0;
    return false;
}

void mapper_trace_mouse_output(
    char const *source,
    uint64_t now_us,
    uint8_t previous_buttons,
    uint8_t mouse_buttons,
    uint32_t input_buttons
) {
#if MAPPER_TRACE_MOUSE_OUTPUT
    if (previous_buttons == mouse_buttons) {
        return;
    }

    char line[256];
    gamepad_freshness_snapshot_t freshness;
    bool input_fresh = gamepad_input_is_fresh(&freshness);
    uint32_t report_age_us =
        (uint32_t)(freshness.now_us - freshness.last_report_us);

    snprintf(
        line,
        sizeof(line),
        "MOUSE_OUT source=%s t_us=%llu prev=%02X buttons=%02X sw_btn=%06lX fresh=%u valid=%u hid=%u age_us=%lu release_pending=%u output_enabled=%u\r\n",
        source,
        (unsigned long long)now_us,
        previous_buttons,
        mouse_buttons,
        (unsigned long)input_buttons,
        input_fresh ? 1 : 0,
        freshness.valid ? 1 : 0,
        freshness.hid_mounted ? 1 : 0,
        (unsigned long)report_age_us,
        g_mapper_release_pending ? 1 : 0,
        g_mapper_output_enabled ? 1 : 0
    );

    cdc_printf_raw(line);
#else
    (void)source;
    (void)now_us;
    (void)previous_buttons;
    (void)mouse_buttons;
    (void)input_buttons;
#endif
}

static bool send_mouse_report_at_output_rate(uint64_t now_us) {
#if PICO_FIRMWARE_MAPPER
    return mapper_action_send_mouse(now_us);
    (void)now_us;
#endif

    uint32_t buttons = g_switch_buttons;

#if PICO_FIRMWARE_MAPPER
    float rx = normalize_switch_axis(g_switch_raw_rx, g_mapper_rx_center);
    float ry = -normalize_switch_axis(g_switch_raw_ry, g_mapper_ry_center);

    if (g_right_calibration_active) {
        rx = 0.0f;
        ry = 0.0f;
        g_mouse_accum_x = 0.0f;
        g_mouse_accum_y = 0.0f;
    } else {
        float right_deadzone = g_mapper_right_deadzone;
        rx = apply_deadzone(rx, right_deadzone);
        ry = apply_deadzone(ry, right_deadzone);
    }
#else
    float rx = apply_deadzone(g_rx, RIGHT_DEADZONE);
    float ry = apply_deadzone(g_ry, RIGHT_DEADZONE);
#endif
    float mouse_speed_x = MOUSE_SPEED_PX_PER_SEC;
    float mouse_speed_y = MOUSE_SPEED_PX_PER_SEC;

#if PICO_FIRMWARE_MAPPER
    if (g_mapper_profile == MAPPER_PROFILE_2) {
        bool rb_held = (buttons & SW_BTN_RB) != 0;

        if (rb_held) {
            mouse_speed_x = PROFILE2_MOUSE_RB_X;
            mouse_speed_y = PROFILE2_MOUSE_RB_Y;
        } else {
            mouse_speed_x = PROFILE2_MOUSE_BASE_X;
            mouse_speed_y = PROFILE2_MOUSE_BASE_Y;
        }

        if (sqrtf(rx * rx + ry * ry) >= PROFILE2_RIGHT_OUTER_THRESHOLD) {
            if (!g_profile2_outer_active || g_profile2_outer_rb != rb_held) {
                g_profile2_outer_active = true;
                g_profile2_outer_rb = rb_held;
                g_profile2_outer_start_us = now_us;
            }

            uint64_t outer_us = now_us - g_profile2_outer_start_us;

            if (rb_held) {
                if (outer_us > PROFILE2_RIGHT_OUTER_RB_DELAY_US) {
                    float accel = clamp_float(
                        (float)(outer_us - PROFILE2_RIGHT_OUTER_RB_DELAY_US) /
                        (float)PROFILE2_RIGHT_OUTER_RB_RAMP_US,
                        0.0f,
                        1.0f
                    );
                    mouse_speed_x += PROFILE2_RIGHT_OUTER_RB_EXTRA_X * accel;
                    mouse_speed_y += PROFILE2_RIGHT_OUTER_RB_EXTRA_Y * accel;
                }
            } else {
                float accel = clamp_float(
                    (float)outer_us / (float)PROFILE2_RIGHT_OUTER_NO_RB_RAMP_US,
                    0.0f,
                    1.0f
                );
                mouse_speed_x += PROFILE2_RIGHT_OUTER_NO_RB_EXTRA_X * accel;
            }
        } else {
            g_profile2_outer_active = false;
            g_profile2_outer_rb = false;
            g_profile2_outer_start_us = 0;
        }
    } else {
        g_profile2_outer_active = false;
        g_profile2_outer_rb = false;
        g_profile2_outer_start_us = 0;
    }
#endif

    float dt = OUTPUT_DT;

    if (g_last_mouse_report_us != 0 && now_us > g_last_mouse_report_us) {
        uint64_t elapsed_us = now_us - g_last_mouse_report_us;

        if (elapsed_us > MOUSE_REPORT_DT_RESET_US) {
            elapsed_us = KEYMOUSE_REPORT_INTERVAL_US;
        }

        dt = (float)elapsed_us / 1000000.0f;
    }

    float next_accum_x = g_mouse_accum_x + rx * mouse_speed_x * dt;
    float next_accum_y = g_mouse_accum_y + ry * mouse_speed_y * dt;

    int move_x = (int)next_accum_x;
    int move_y = (int)next_accum_y;

    next_accum_x -= (float)move_x;
    next_accum_y -= (float)move_y;

    move_x = clamp_int(move_x, -127, 127);
    move_y = clamp_int(move_y, -127, 127);

    uint8_t mouse_buttons = 0;

    bool rb_left_down = mouse_button_down_with_grace(
        (buttons & SW_BTN_RB) != 0,
        now_us,
        &g_mouse_left_release_deadline_us
    );

    if (rb_left_down) {
        mouse_buttons |= MOUSE_BUTTON_LEFT;
    }

    bool lb_right_down = mouse_button_down_with_grace(
        (buttons & SW_BTN_LB) != 0,
        now_us,
        &g_mouse_right_release_deadline_us
    );

    if (lb_right_down || snapshot_macro_right_down(now_us)) {
        mouse_buttons |= MOUSE_BUTTON_RIGHT;
    }

#if PICO_FIRMWARE_MAPPER
    bool suppress_y_middle = false;

    if (g_mapper_profile != MAPPER_PROFILE_3 &&
        (buttons & SW_BTN_LT) &&
        (buttons & SW_BTN_RT) &&
        (buttons & SW_BTN_Y)) {
        suppress_y_middle = true;
    }

    if (g_mapper_profile == MAPPER_PROFILE_2 &&
        (buttons & SW_BTN_LSTICK) &&
        (buttons & SW_BTN_Y)) {
        suppress_y_middle = true;
    }

    if ((buttons & SW_BTN_Y) && !suppress_y_middle) {
        mouse_buttons |= MOUSE_BUTTON_MIDDLE;
    }
#endif

    int wheel = clamp_int(g_pending_wheel, -127, 127);
    uint8_t previous_mouse_buttons = g_last_mouse_buttons;

    if (!tud_hid_n_mouse_report(
        HID_INSTANCE_MOUSE,
        0,
        mouse_buttons,
        (int8_t)move_x,
        (int8_t)move_y,
        (int8_t)wheel,
        0
    )) {
        return false;
    }

    mapper_trace_mouse_output("normal", now_us, previous_mouse_buttons, mouse_buttons, buttons);

    g_mouse_accum_x = next_accum_x;
    g_mouse_accum_y = next_accum_y;
    g_last_mouse_buttons = mouse_buttons;
    g_last_mouse_report_us = now_us;
    g_pending_wheel -= (int16_t)wheel;

    return true;
}

static bool send_mouse_neutral_report(uint64_t now_us) {
    uint8_t previous_mouse_buttons = g_last_mouse_buttons;

    if (!tud_hid_n_mouse_report(HID_INSTANCE_MOUSE, 0, 0, 0, 0, 0, 0)) {
        return false;
    }

    mapper_trace_mouse_output("neutral", now_us, previous_mouse_buttons, 0, g_switch_buttons);

    g_mouse_accum_x = 0.0f;
    g_mouse_accum_y = 0.0f;
    g_last_mouse_buttons = 0;
    g_last_mouse_report_us = now_us;
    g_mouse_left_release_deadline_us = 0;
    g_mouse_right_release_deadline_us = 0;
    g_stale_mouse_release_deadline_us = 0;
    g_pending_wheel = 0;

    return true;
}

static bool send_mouse_stale_hold_report(uint64_t now_us) {
    uint8_t previous_mouse_buttons = g_last_mouse_buttons;

    if (previous_mouse_buttons == 0) {
        return false;
    }

    if (!tud_hid_n_mouse_report(HID_INSTANCE_MOUSE, 0, previous_mouse_buttons, 0, 0, 0, 0)) {
        return false;
    }

    mapper_trace_mouse_output("stale_hold", now_us, previous_mouse_buttons, previous_mouse_buttons, g_switch_buttons);

    g_mouse_accum_x = 0.0f;
    g_mouse_accum_y = 0.0f;
    g_last_mouse_report_us = now_us;
    g_pending_wheel = 0;

    return true;
}

static bool mapper_keyboard_is_neutral(void) {
    uint8_t keycode[6] = {0, 0, 0, 0, 0, 0};

    return g_last_modifier == 0 && keycodes_match(g_last_keycode, keycode);
}

static bool send_mapper_neutral_step(uint64_t now_us) {
    bool report_queued = false;

    if (!mapper_keyboard_is_neutral()) {
        report_queued = send_keyboard_neutral_if_needed();
    }

    if (g_last_mouse_buttons != 0 || g_pending_wheel != 0) {
        report_queued = send_mouse_neutral_report(now_us) || report_queued;
    }

    if (report_queued) {
        return true;
    }

    g_mapper_release_pending = false;
    g_mouse_accum_x = 0.0f;
    g_mouse_accum_y = 0.0f;
    g_last_mouse_report_us = 0;
    g_mouse_left_release_deadline_us = 0;
    g_mouse_right_release_deadline_us = 0;
    g_stale_mouse_release_deadline_us = 0;
    return false;
}

#if PICO_FIRMWARE_MAPPER
static bool __no_inline_not_in_flash_func(read_bootsel_button_pressed)(void) {
    const uint cs_pin_index = 1;
    const uint32_t cs_bit = 1u << 1;
    uint32_t flags = save_and_disable_interrupts();

    hw_write_masked(
        &ioqspi_hw->io[cs_pin_index].ctrl,
        GPIO_OVERRIDE_LOW << IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_LSB,
        IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_BITS
    );

    for (volatile int i = 0; i < 1000; i++) {
        tight_loop_contents();
    }

    bool pressed = (sio_hw->gpio_hi_in & cs_bit) == 0;

    hw_write_masked(
        &ioqspi_hw->io[cs_pin_index].ctrl,
        GPIO_OVERRIDE_NORMAL << IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_LSB,
        IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_BITS
    );

    restore_interrupts(flags);

    return pressed;
}

static bool pico_button_pressed(void) {
    if (!multicore_lockout_start_timeout_us(200)) {
        return false;
    }

    bool pressed = read_bootsel_button_pressed();
    multicore_lockout_end_blocking();

    return pressed;
}

static void mapper_cycle_profile(void) {
    mapper_action_cycle_profile();
    g_mapper_profile =
        (mapper_profile_t)mapper_config_get()->settings.active_profile;
    mapper_request_output_release();
}

static void mapper_toggle_output(void) {
    mapper_action_toggle_output();
    g_mapper_output_enabled = mapper_action_output_enabled();
    mapper_request_output_release();
}

static void right_calibration_start(uint64_t now_us) {
    g_right_calibration_active = true;
    mapper_action_set_calibration_active(true);
    g_right_calibration_end_us = now_us + RIGHT_CALIBRATION_WINDOW_US;
    g_right_calibration_next_sample_us = now_us;
    g_right_calibration_sum_rx = 0;
    g_right_calibration_sum_ry = 0;
    g_right_calibration_samples = 0;
    g_right_calibration_min_rx = 4095;
    g_right_calibration_max_rx = 0;
    g_right_calibration_min_ry = 4095;
    g_right_calibration_max_ry = 0;
    g_profile2_outer_active = false;
    g_profile2_outer_rb = false;
    g_profile2_outer_start_us = 0;
    mapper_request_output_release();
}

void mapper_calibration_start(void) {
    right_calibration_start(time_us_64());
}

bool mapper_calibration_status(uint16_t *center_x, uint16_t *center_y,
                               float *deadzone, uint32_t *remaining_ms) {
    mapper_settings_t *settings = &mapper_config_get()->settings;
    if (center_x != NULL) {
        *center_x = settings->right_center_x;
    }
    if (center_y != NULL) {
        *center_y = settings->right_center_y;
    }
    if (deadzone != NULL) {
        *deadzone = settings->right_deadzone;
    }
    if (remaining_ms != NULL) {
        uint64_t now_us = time_us_64();
        *remaining_ms = g_right_calibration_active && g_right_calibration_end_us > now_us ?
            (uint32_t)((g_right_calibration_end_us - now_us + 999u) / 1000u) : 0u;
    }
    return g_right_calibration_active;
}

static void right_calibration_finish(void) {
    if (g_right_calibration_samples != 0) {
        uint32_t rx_center = (uint32_t)(
            (g_right_calibration_sum_rx + g_right_calibration_samples / 2u) /
            g_right_calibration_samples
        );
        uint32_t ry_center = (uint32_t)(
            (g_right_calibration_sum_ry + g_right_calibration_samples / 2u) /
            g_right_calibration_samples
        );
        uint16_t rx_center_u16 = (uint16_t)clamp_int((int)rx_center, 1, 4094);
        uint16_t ry_center_u16 = (uint16_t)clamp_int((int)ry_center, 1, 4094);

        g_mapper_rx_center = rx_center_u16;
        g_mapper_ry_center = ry_center_u16;

        float measured_deadzone = 0.0f;
        measured_deadzone = fmaxf(
            measured_deadzone,
            fabsf(normalize_switch_axis(g_right_calibration_min_rx, rx_center_u16))
        );
        measured_deadzone = fmaxf(
            measured_deadzone,
            fabsf(normalize_switch_axis(g_right_calibration_max_rx, rx_center_u16))
        );
        measured_deadzone = fmaxf(
            measured_deadzone,
            fabsf(normalize_switch_axis(g_right_calibration_min_ry, ry_center_u16))
        );
        measured_deadzone = fmaxf(
            measured_deadzone,
            fabsf(normalize_switch_axis(g_right_calibration_max_ry, ry_center_u16))
        );
        g_mapper_right_deadzone = measured_deadzone;
    }

    g_right_calibration_active = false;
    mapper_action_set_calibration_active(false);
    g_right_calibration_end_us = 0;
    g_right_calibration_next_sample_us = 0;
    g_right_calibration_sum_rx = 0;
    g_right_calibration_sum_ry = 0;
    g_right_calibration_samples = 0;
    g_right_calibration_min_rx = 4095;
    g_right_calibration_max_rx = 0;
    g_right_calibration_min_ry = 4095;
    g_right_calibration_max_ry = 0;
    g_mouse_accum_x = 0.0f;
    g_mouse_accum_y = 0.0f;
    g_last_mouse_report_us = 0;
    mapper_action_set_calibration(g_mapper_rx_center, g_mapper_ry_center,
                                  g_mapper_right_deadzone);

    mapper_request_output_release();
}

static void right_calibration_task(uint64_t now_us) {
    if (!g_right_calibration_active) {
        return;
    }

    if (now_us >= g_right_calibration_next_sample_us &&
        now_us <= g_right_calibration_end_us &&
        gamepad_input_is_fresh(NULL)) {
        mapper_input_state_t input;
        mapper_input_snapshot(&input);
        uint16_t raw_rx = input.raw_rx;
        uint16_t raw_ry = input.raw_ry;

        g_right_calibration_sum_rx += raw_rx;
        g_right_calibration_sum_ry += raw_ry;
        if (raw_rx < g_right_calibration_min_rx) {
            g_right_calibration_min_rx = raw_rx;
        }
        if (raw_rx > g_right_calibration_max_rx) {
            g_right_calibration_max_rx = raw_rx;
        }
        if (raw_ry < g_right_calibration_min_ry) {
            g_right_calibration_min_ry = raw_ry;
        }
        if (raw_ry > g_right_calibration_max_ry) {
            g_right_calibration_max_ry = raw_ry;
        }
        g_right_calibration_samples++;
        g_right_calibration_next_sample_us += RIGHT_CALIBRATION_SAMPLE_INTERVAL_US;

        if (now_us > g_right_calibration_next_sample_us + RIGHT_CALIBRATION_SAMPLE_INTERVAL_US) {
            g_right_calibration_next_sample_us = now_us + RIGHT_CALIBRATION_SAMPLE_INTERVAL_US;
        }
    }

    if (now_us >= g_right_calibration_end_us) {
        right_calibration_finish();
    }
}

static void pico_button_handle_release(uint64_t now_us) {
    if (g_pico_button_click_pending && now_us < g_pico_button_click_deadline_us) {
        g_pico_button_click_pending = false;
        mapper_toggle_output();
        return;
    }

    g_pico_button_click_pending = true;
    g_pico_button_click_deadline_us = now_us + DOUBLE_CLICK_US;
}

static void pico_button_task(uint64_t now_us) {
    if (now_us < g_pico_button_next_sample_us) {
        return;
    }

    g_pico_button_next_sample_us = now_us + PICO_BUTTON_SAMPLE_INTERVAL_US;

    bool raw_pressed = pico_button_pressed();

    if (raw_pressed != g_pico_button_raw) {
        g_pico_button_raw = raw_pressed;
        g_pico_button_debounce_deadline_us = now_us + PICO_BUTTON_DEBOUNCE_US;
    }

    if (now_us >= g_pico_button_debounce_deadline_us &&
        g_pico_button_stable != g_pico_button_raw) {
        bool was_pressed = g_pico_button_stable;
        g_pico_button_stable = g_pico_button_raw;

        if (!was_pressed && g_pico_button_stable) {
            g_pico_button_press_start_us = now_us;
            g_pico_button_long_press_handled = false;
        } else if (was_pressed && !g_pico_button_stable) {
            if (g_pico_button_long_press_handled) {
                g_pico_button_long_press_handled = false;
                g_pico_button_press_start_us = 0;
                return;
            }

            pico_button_handle_release(now_us);
        }
    }

    if (g_pico_button_stable &&
        !g_pico_button_long_press_handled &&
        g_pico_button_press_start_us != 0 &&
        now_us - g_pico_button_press_start_us >= PICO_BUTTON_LONG_PRESS_US) {
        g_pico_button_long_press_handled = true;
        g_pico_button_click_pending = false;
        right_calibration_start(now_us);
    }

    if (g_pico_button_click_pending && now_us >= g_pico_button_click_deadline_us) {
        g_pico_button_click_pending = false;
        mapper_cycle_profile();
    }
}
#endif

// ============================================================
// Gamepad input parsing
// ============================================================

static bool u8_axis_near_center(uint8_t value) {
    return value >= 124u && value <= 132u;
}

static bool u12_axis_near_center(uint16_t value) {
    return value >= 1920u && value <= 2176u;
}

static void reset_dpad_up_idle_disconnect_guard(void) {
    g_dpad_up_idle_guard_start_us = 0;
    g_dpad_up_idle_guard_blocked = false;
}

static bool dpad_up_idle_disconnect_guard(bool looks_like_dpad_up_idle) {
    if (!looks_like_dpad_up_idle) {
        reset_dpad_up_idle_disconnect_guard();
        return false;
    }

    if (g_dpad_up_idle_guard_blocked) {
        return true;
    }

    uint64_t now_us = time_us_64();

    if (g_dpad_up_idle_guard_start_us == 0) {
        g_dpad_up_idle_guard_start_us = now_us;
        return false;
    }

    if (now_us - g_dpad_up_idle_guard_start_us < DPAD_UP_IDLE_DISCONNECT_GUARD_US) {
        return false;
    }

    g_dpad_up_idle_guard_blocked = true;
    clear_gamepad_state();
    return true;
}

static bool legacy_report_looks_disconnected(uint8_t const *report, uint16_t len) {
    if (len <= BUTTON_BYTE_9) {
        return false;
    }

    for (uint8_t i = DPAD_BYTE; i <= BUTTON_BYTE_9; i++) {
        if (report[i] != 0) {
            return false;
        }
    }

    // Ignore transient fake-disconnect packets; timeout handles real disconnects.
    return true;
}

static bool process_legacy_gamepad_report(uint8_t const *report, uint16_t len) {
    if (len <= BUTTON_BYTE_9) {
        return false;
    }

    if (legacy_report_looks_disconnected(report, len)) {
        return false;
    }

    uint8_t dpad = report[DPAD_BYTE] & DPAD_MASK;
    uint8_t b8 = report[BUTTON_BYTE_8];
    uint8_t b9 = report[BUTTON_BYTE_9];
    bool dpad_up_idle = dpad == 0x00 &&
                         u8_axis_near_center(report[AXIS_LX_BYTE]) &&
                         u8_axis_near_center(report[AXIS_LY_BYTE]) &&
                         u8_axis_near_center(report[AXIS_RX_BYTE]) &&
                         u8_axis_near_center(report[AXIS_RY_BYTE]) &&
                         report[AXIS_RT_BYTE] == 0 &&
                         report[AXIS_LT_BYTE] == 0 &&
                         b8 == 0 &&
                         b9 == 0;

    if (dpad_up_idle_disconnect_guard(dpad_up_idle)) {
        return false;
    }

    float lx = normalize_u8_axis(report[AXIS_LX_BYTE]);
    float ly = normalize_u8_axis(report[AXIS_LY_BYTE]);
    float rx = normalize_u8_axis(report[AXIS_RX_BYTE]);
    float ry = normalize_u8_axis(report[AXIS_RY_BYTE]);

#if INVERT_LX
    lx = -lx;
#endif

#if INVERT_LY
    ly = -ly;
#endif

#if INVERT_RX
    rx = -rx;
#endif

#if INVERT_RY
    ry = -ry;
#endif

    float rt = (float)report[AXIS_RT_BYTE] / 255.0f;
    float lt = (float)report[AXIS_LT_BYTE] / 255.0f;

    critical_section_enter_blocking(&g_mapper_input_lock);

    g_lx = lx;
    g_ly = ly;
    g_rx = rx;
    g_ry = ry;

    g_dpad = dpad;

    g_rt_analog = rt;
    g_lt_analog = lt;

    g_a = (b8 & BUTTON_A_MASK) != 0;
    g_b = (b8 & BUTTON_B_MASK) != 0;
    g_r5 = (b8 & BUTTON_R5_MASK) != 0;
    g_x = (b8 & BUTTON_X_MASK) != 0;
    g_y = (b8 & BUTTON_Y_MASK) != 0;

    g_lb = (b8 & BUTTON_LB_MASK) != 0;
    g_rb = (b8 & BUTTON_RB_MASK) != 0;

    g_lt_digital = (b9 & BUTTON_LT_DIGITAL_MASK) != 0;
    g_rt_digital = (b9 & BUTTON_RT_DIGITAL_MASK) != 0;

    g_setting = (b9 & BUTTON_SETTING_MASK) != 0;
    g_menu = (b9 & BUTTON_MENU_MASK) != 0;

    g_l3 = (b9 & BUTTON_L3_MASK) != 0;
    g_r3 = (b9 & BUTTON_R3_MASK) != 0;

    uint32_t buttons = 0;

    if (g_y) {
        buttons |= SW_BTN_Y;
    }

    if (g_x) {
        buttons |= SW_BTN_X;
    }

    if (g_b) {
        buttons |= SW_BTN_B;
    }

    if (g_a) {
        buttons |= SW_BTN_A;
    }

    if (g_rb) {
        buttons |= SW_BTN_RB;
    }

    if (g_rt_digital) {
        buttons |= SW_BTN_RT;
    }

    if (g_menu) {
        buttons |= SW_BTN_MENU;
    }

    if (g_setting) {
        buttons |= SW_BTN_OPTION;
    }

    if (g_r3) {
        buttons |= SW_BTN_RSTICK;
    }

    if (g_l3) {
        buttons |= SW_BTN_LSTICK;
    }

    switch (dpad) {
        case 0x00:
            buttons |= SW_BTN_DPAD_UP;
            break;

        case 0x01:
            buttons |= SW_BTN_DPAD_UP | SW_BTN_DPAD_RIGHT;
            break;

        case 0x02:
            buttons |= SW_BTN_DPAD_RIGHT;
            break;

        case 0x03:
            buttons |= SW_BTN_DPAD_DOWN | SW_BTN_DPAD_RIGHT;
            break;

        case 0x04:
            buttons |= SW_BTN_DPAD_DOWN;
            break;

        case 0x05:
            buttons |= SW_BTN_DPAD_DOWN | SW_BTN_DPAD_LEFT;
            break;

        case 0x06:
            buttons |= SW_BTN_DPAD_LEFT;
            break;

        case 0x07:
            buttons |= SW_BTN_DPAD_UP | SW_BTN_DPAD_LEFT;
            break;

        default:
            break;
    }

    if (g_lb) {
        buttons |= SW_BTN_LB;
    }

    if (g_lt_digital) {
        buttons |= SW_BTN_LT;
    }

    g_switch_buttons = buttons;
    g_switch_raw_lx = scale_u8_to_u12(report[AXIS_LX_BYTE]);
    g_switch_raw_ly = scale_u8_to_u12(report[AXIS_LY_BYTE]);
    g_switch_raw_rx = scale_u8_to_u12(report[AXIS_RX_BYTE]);
    g_switch_raw_ry = scale_u8_to_u12(report[AXIS_RY_BYTE]);
    g_gamepad_valid = true;
    g_last_valid_report_us = time_us_32();

    critical_section_exit(&g_mapper_input_lock);

    return true;
}

static bool process_switch_pro_report(uint8_t const *report, uint16_t len) {
    if (len < 12) {
        return false;
    }

    if (report[0] != JC_INPUT_IMU_DATA &&
        report[0] != JC_INPUT_SUBCMD_REPLY &&
        report[0] != JC_INPUT_MCU_DATA) {
        return false;
    }

    uint32_t buttons = (uint32_t)report[3] |
                       ((uint32_t)report[4] << 8) |
                       ((uint32_t)report[5] << 16);

    uint16_t raw_lx = switch_stick_x(&report[6]);
    uint16_t raw_ly = switch_stick_y(&report[6]);
    uint16_t raw_rx = switch_stick_x(&report[9]);
    uint16_t raw_ry = switch_stick_y(&report[9]);

    if (buttons == 0 &&
        raw_lx == 0 &&
        raw_ly == 0 &&
        raw_rx == 0 &&
        raw_ry == 0) {
        // Ignore transient fake-disconnect packets; timeout handles real disconnects.
        return false;
    }

    uint32_t buttons_without_neutral = buttons & ~SWITCH_PRO_NEUTRAL_BUTTON;
    bool dpad_up_idle = buttons_without_neutral == SW_BTN_DPAD_UP &&
                         u12_axis_near_center(raw_lx) &&
                         u12_axis_near_center(raw_ly) &&
                         u12_axis_near_center(raw_rx) &&
                         u12_axis_near_center(raw_ry);

    if (dpad_up_idle_disconnect_guard(dpad_up_idle)) {
        return false;
    }

#if PICO_FIRMWARE_MAPPER
    float lx = normalize_switch_axis(raw_lx, 2048);
    float ly = -normalize_switch_axis(raw_ly, 2048);
    float rx = normalize_switch_axis(raw_rx, g_mapper_rx_center);
    float ry = -normalize_switch_axis(raw_ry, g_mapper_ry_center);
#else
    if (!g_switch_centered) {
        g_switch_lx_center = raw_lx;
        g_switch_ly_center = raw_ly;
        g_switch_rx_center = raw_rx;
        g_switch_ry_center = raw_ry;
        g_switch_centered = true;
    }

    float lx = normalize_switch_axis(raw_lx, g_switch_lx_center);
    float ly = -normalize_switch_axis(raw_ly, g_switch_ly_center);
    float rx = normalize_switch_axis(raw_rx, g_switch_rx_center);
    float ry = -normalize_switch_axis(raw_ry, g_switch_ry_center);
#endif

#if INVERT_LX
    lx = -lx;
#endif

#if INVERT_LY
    ly = -ly;
#endif

#if INVERT_RX
    rx = -rx;
#endif

#if INVERT_RY
    ry = -ry;
#endif

    critical_section_enter_blocking(&g_mapper_input_lock);

    g_lx = lx;
    g_ly = ly;
    g_rx = rx;
    g_ry = ry;

    g_switch_buttons = buttons;
    g_switch_raw_lx = raw_lx;
    g_switch_raw_ly = raw_ly;
    g_switch_raw_rx = raw_rx;
    g_switch_raw_ry = raw_ry;

    g_a = (buttons & SW_BTN_A) != 0;
    g_b = (buttons & SW_BTN_B) != 0;
    g_x = (buttons & SW_BTN_X) != 0;
    g_y = (buttons & SW_BTN_Y) != 0;
    g_lb = (buttons & SW_BTN_LB) != 0;
    g_rb = (buttons & SW_BTN_RB) != 0;
    g_lt_digital = (buttons & SW_BTN_LT) != 0;
    g_rt_digital = (buttons & SW_BTN_RT) != 0;
    g_menu = (buttons & SW_BTN_MENU) != 0;
    g_setting = (buttons & SW_BTN_OPTION) != 0;
    g_r3 = (buttons & SW_BTN_RSTICK) != 0;
    g_l3 = (buttons & SW_BTN_LSTICK) != 0;
    g_gamepad_valid = true;
    g_last_valid_report_us = time_us_32();

    critical_section_exit(&g_mapper_input_lock);

    return true;
}
void mapper_input_snapshot(mapper_input_state_t *state) {
    if (state == NULL) {
        return;
    }

    critical_section_enter_blocking(&g_mapper_input_lock);
    state->buttons = g_switch_buttons;
    state->lx = g_lx;
    state->ly = g_ly;
    state->rx = g_rx;
    state->ry = g_ry;
    state->raw_lx = g_switch_raw_lx;
    state->raw_ly = g_switch_raw_ly;
    state->raw_rx = g_switch_raw_rx;
    state->raw_ry = g_switch_raw_ry;
    critical_section_exit(&g_mapper_input_lock);
}



static bool gamepad_input_is_fresh(gamepad_freshness_snapshot_t *snapshot_out) {
    gamepad_freshness_snapshot_t snapshot;

    /* Core 1 publishes the parsed input and its timestamp together. Snapshot
     * both under the same lock, then read the clock. Reading the clock first
     * lets a new Core 1 report land in between; subtracting that newer report
     * timestamp from the older clock value wraps uint32_t and looks like a
     * multi-second timeout for one output tick. */
    critical_section_enter_blocking(&g_mapper_input_lock);
    snapshot.valid = g_gamepad_valid;
    snapshot.last_report_us = g_last_valid_report_us;
    critical_section_exit(&g_mapper_input_lock);

    snapshot.hid_mounted = g_host_hid_mounted;
    snapshot.now_us = time_us_32();

    if (snapshot_out != NULL) {
        *snapshot_out = snapshot;
    }

    return snapshot.valid &&
           snapshot.hid_mounted &&
           (uint32_t)(snapshot.now_us - snapshot.last_report_us) <=
               GAMEPAD_REPORT_TIMEOUT_US;
}

static void process_gamepad_report(uint8_t const *report, uint16_t len) {
    g_host_hid_report_count++;

    debug_print_hex_report(report, len);

    bool parsed;

    if (is_switch_pro_controller(g_host_vid, g_host_pid)) {
        parsed = process_switch_pro_report(report, len);
    } else {
        parsed = process_legacy_gamepad_report(report, len);
    }

    (void)parsed;
}

static uint8_t g_switch_output_payload[16];

static bool host_send_output_report(
    uint8_t dev_addr,
    uint8_t instance,
    uint8_t report_id,
    uint8_t const *payload,
    uint16_t payload_len
) {
    g_switch_out_submit_count++;

    if (tuh_hid_send_report(dev_addr, instance, report_id, payload, payload_len)) {
        g_switch_out_ep_submit_count++;
        g_switch_output_pending = true;
        g_switch_output_deadline_us = time_us_64() + SWITCH_OUTPUT_COMPLETE_TIMEOUT_US;
        return true;
    }

    g_switch_out_ep_fail_count++;

    if (tuh_hid_set_report(
        dev_addr,
        instance,
        report_id,
        HID_REPORT_TYPE_OUTPUT,
        (void *)payload,
        payload_len
    )) {
        g_switch_out_ctrl_submit_count++;
        g_switch_output_pending = true;
        g_switch_output_deadline_us = time_us_64() + SWITCH_OUTPUT_COMPLETE_TIMEOUT_US;
        return true;
    }

    g_switch_init_send_fail_count++;
    return false;
}

static bool switch_send_usb_cmd(uint8_t cmd) {
    g_switch_output_payload[0] = cmd;

    return host_send_output_report(
        g_host_dev_addr,
        g_host_hid_instance,
        JC_OUTPUT_USB_CMD,
        g_switch_output_payload,
        1
    );
}

static bool switch_send_subcmd_data(
    uint8_t subcmd,
    uint8_t const *data,
    uint8_t data_len
) {
    static uint8_t const neutral_rumble[8] = {
        0x00, 0x01, 0x40, 0x40,
        0x00, 0x01, 0x40, 0x40
    };

    if ((uint16_t)10 + data_len > sizeof(g_switch_output_payload)) {
        return false;
    }

    g_switch_output_payload[0] = g_switch_subcmd_packet++ & 0x0F;
    memcpy(&g_switch_output_payload[1], neutral_rumble, sizeof(neutral_rumble));
    g_switch_output_payload[9] = subcmd;

    if (data_len > 0) {
        memcpy(&g_switch_output_payload[10], data, data_len);
    }

    return host_send_output_report(
        g_host_dev_addr,
        g_host_hid_instance,
        JC_OUTPUT_RUMBLE_AND_SUBCMD,
        g_switch_output_payload,
        (uint16_t)10 + data_len
    );
}

static bool switch_send_subcmd(uint8_t subcmd, uint8_t value) {
    return switch_send_subcmd_data(subcmd, &value, 1);
}

static void capture_start(char const *command) {
    size_t start = 0;
    size_t end = strlen(command);

    while (start < end && (command[start] == ' ' || command[start] == '\t')) {
        start++;
    }

    while (end > start && (command[end - 1] == ' ' || command[end - 1] == '\t')) {
        end--;
    }

    size_t label_len = end - start;

    if (label_len == 0) {
        memcpy(g_capture_label, "sample", 7);
    } else {
        if (label_len >= sizeof(g_capture_label)) {
            label_len = sizeof(g_capture_label) - 1;
        }

        memcpy(g_capture_label, &command[start], label_len);
        g_capture_label[label_len] = '\0';
    }

    g_capture_active = true;
    g_capture_sample_index = 0;
    g_capture_next_sample_us = time_us_64() + CAPTURE_START_DELAY_US;

    char line[192];

    snprintf(
        line,
        sizeof(line),
        "CAPTURE_BEGIN label=%s count=%u start_delay_ms=%u interval_ms=%u\r\n",
        g_capture_label,
        CAPTURE_SAMPLE_COUNT,
        CAPTURE_START_DELAY_US / 1000u,
        CAPTURE_INTERVAL_US / 1000u
    );

    cdc_printf_raw(line);
}

static void cdc_process_command_char(char ch) {
    if (ch == '\r' || ch == '\n') {
        if (g_cdc_command_len > 0) {
            g_cdc_command[g_cdc_command_len] = '\0';

            if (strcmp(g_cdc_command, "rescan") == 0 ||
                strcmp(g_cdc_command, "RESCAN") == 0) {
                request_host_rescan();
                cdc_printf_raw("HOST_RESCAN_REQUESTED\r\n");
            } else {
                capture_start(g_cdc_command);
            }

            g_cdc_command_len = 0;
        }

        return;
    }

    if (g_cdc_command_len < sizeof(g_cdc_command) - 1) {
        g_cdc_command[g_cdc_command_len++] = ch;
    } else {
        g_cdc_command[g_cdc_command_len] = '\0';
        capture_start(g_cdc_command);
        g_cdc_command_len = 0;
    }
}

static void cdc_command_task(void) {
    while (tud_cdc_available()) {
        char buf[64];
        uint32_t count = tud_cdc_read(buf, sizeof(buf));

        for (uint32_t i = 0; i < count; i++) {
            cdc_process_command_char(buf[i]);
        }
    }
}

static void capture_print_sample(void) {
    uint8_t report[DEBUG_MAX_REPORT_LEN];
    uint16_t len = 0;
    uint32_t seq = 0;
    uint64_t report_time_us = 0;
    uint8_t dev_addr = 0;
    uint8_t instance = 0;
    bool has_report = snapshot_latest_report(
        report,
        &len,
        &seq,
        &report_time_us,
        &dev_addr,
        &instance
    );
    char line[768];
    int pos = 0;

    if (!has_report) {
        snprintf(
            line,
            sizeof(line),
            "CAPTURE label=%s sample=%u/%u NO_REPORT host_reports=%lu\r\n",
            g_capture_label,
            g_capture_sample_index + 1,
            CAPTURE_SAMPLE_COUNT,
            (unsigned long)g_host_hid_report_count
        );
        cdc_printf_raw(line);
        return;
    }

    /* The report timestamp is written by Core 1. Read the clock only after
     * taking the locked report snapshot so age cannot underflow if a report
     * arrives between the two reads. */
    uint64_t now_us = time_us_64();
    uint64_t age_us = now_us - report_time_us;

    pos += snprintf(
        line + pos,
        sizeof(line) - pos,
        "CAPTURE label=%s sample=%u/%u seq=%lu age_us=%llu dev=%u inst=%u len=%u ",
        g_capture_label,
        g_capture_sample_index + 1,
        CAPTURE_SAMPLE_COUNT,
        (unsigned long)seq,
        (unsigned long long)age_us,
        dev_addr,
        instance,
        len
    );

    if (is_switch_pro_controller(g_host_vid, g_host_pid) &&
        len >= 12 &&
        (report[0] == JC_INPUT_IMU_DATA ||
         report[0] == JC_INPUT_SUBCMD_REPLY ||
         report[0] == JC_INPUT_MCU_DATA)) {
        uint32_t buttons = (uint32_t)report[3] |
                           ((uint32_t)report[4] << 8) |
                           ((uint32_t)report[5] << 16);
        uint16_t raw_lx = switch_stick_x(&report[6]);
        uint16_t raw_ly = switch_stick_y(&report[6]);
        uint16_t raw_rx = switch_stick_x(&report[9]);
        uint16_t raw_ry = switch_stick_y(&report[9]);

        pos += snprintf(
            line + pos,
            sizeof(line) - pos,
            "sw_btn=%06lX L=%u,%u R=%u,%u ",
            (unsigned long)buttons,
            raw_lx,
            raw_ly,
            raw_rx,
            raw_ry
        );
    } else if (len > BUTTON_BYTE_9) {
        pos += snprintf(
            line + pos,
            sizeof(line) - pos,
            "u8_dpad=%02X L=%u,%u R=%u,%u b8=%02X b9=%02X ",
            report[DPAD_BYTE] & DPAD_MASK,
            report[AXIS_LX_BYTE],
            report[AXIS_LY_BYTE],
            report[AXIS_RX_BYTE],
            report[AXIS_RY_BYTE],
            report[BUTTON_BYTE_8],
            report[BUTTON_BYTE_9]
        );
    }

    pos += snprintf(line + pos, sizeof(line) - pos, "raw=");

    for (uint16_t i = 0; i < len && pos < (int)sizeof(line) - 5; i++) {
        pos += snprintf(line + pos, sizeof(line) - pos, "%02X", report[i]);

        if (i + 1 < len) {
            pos += snprintf(line + pos, sizeof(line) - pos, " ");
        }
    }

    snprintf(line + pos, sizeof(line) - pos, "\r\n");
    cdc_printf_raw(line);
}

static void capture_task(void) {
    if (!g_capture_active) {
        return;
    }

    uint64_t now_us = time_us_64();

    if (now_us < g_capture_next_sample_us) {
        return;
    }

    capture_print_sample();
    g_capture_sample_index++;

    if (g_capture_sample_index >= CAPTURE_SAMPLE_COUNT) {
        char line[96];

        snprintf(line, sizeof(line), "CAPTURE_END label=%s\r\n", g_capture_label);
        cdc_printf_raw(line);
        g_capture_active = false;
        return;
    }

    g_capture_next_sample_us += CAPTURE_INTERVAL_US;

    if (now_us > g_capture_next_sample_us + CAPTURE_INTERVAL_US) {
        g_capture_next_sample_us = now_us + CAPTURE_INTERVAL_US;
    }
}

static bool switch_init_step_is_optional(uint8_t step) {
    return step == SWITCH_INIT_USB_BAUDRATE ||
           step == SWITCH_INIT_REQ_DEV_INFO;
}

static uint8_t switch_init_max_retries(uint8_t step) {
    return switch_init_step_is_optional(step) ?
           SWITCH_INIT_OPTIONAL_RETRIES :
           SWITCH_INIT_MAX_RETRIES;
}

static void switch_init_advance(void) {
    g_switch_wait_ack_kind = SWITCH_ACK_NONE;
    g_switch_wait_ack_id = 0;
    g_switch_init_retry_count = 0;
    g_switch_output_pending = false;

    if (g_switch_init_step == SWITCH_INIT_SET_REPORT_MODE) {
        g_switch_init_step = SWITCH_INIT_IDLE;
    } else if (g_switch_init_step != SWITCH_INIT_IDLE &&
               g_switch_init_step != SWITCH_INIT_FAILED) {
        g_switch_init_step++;
    }

    g_switch_next_init_us = time_us_64() + SWITCH_INIT_STEP_DELAY_US;
}

static void switch_init_fail_or_continue(void) {
    if (switch_init_step_is_optional(g_switch_init_step)) {
        switch_init_advance();
        return;
    }

    g_switch_init_fail_count++;
    g_switch_init_step = SWITCH_INIT_FAILED;
    g_switch_wait_ack_kind = SWITCH_ACK_NONE;
    g_switch_wait_ack_id = 0;
    g_switch_output_pending = false;
    g_switch_next_init_us = time_us_64() + SWITCH_INIT_RESTART_DELAY_US;
}

static void switch_init_wait_for_ack(uint8_t ack_kind, uint8_t ack_id) {
    g_switch_wait_ack_kind = ack_kind;
    g_switch_wait_ack_id = ack_id;
    g_switch_wait_deadline_us = time_us_64() + SWITCH_INIT_ACK_TIMEOUT_US;
}

static bool switch_usb_response_matches(uint8_t const *report, uint16_t len, uint8_t cmd) {
    bool matched = false;

    if (len > 1) {
        g_switch_last_usb_ack_1 = report[1];

        if (report[1] == cmd) {
            matched = true;
        }
    }

    if (len > 3) {
        g_switch_last_usb_ack_3 = report[3];

        if (report[3] == cmd) {
            matched = true;
        }
    }

    return matched;
}

static void switch_handle_init_report(uint8_t const *report, uint16_t len) {
    if (!is_switch_pro_controller(g_host_vid, g_host_pid) || len == 0) {
        return;
    }

    if (report[0] == JC_INPUT_USB_RESPONSE) {
        g_switch_usb_response_count++;

        if (g_switch_wait_ack_kind == SWITCH_ACK_USB &&
            switch_usb_response_matches(report, len, g_switch_wait_ack_id)) {
            g_switch_usb_ack_count++;
            switch_init_advance();
        } else {
            (void)switch_usb_response_matches(report, len, g_switch_wait_ack_id);
        }

        return;
    }

    if (report[0] == JC_INPUT_SUBCMD_REPLY && len > 14) {
        g_switch_subcmd_response_count++;
        g_switch_last_subcmd_ack = report[13];
        g_switch_last_subcmd_id = report[14];

        if (g_switch_wait_ack_kind == SWITCH_ACK_SUBCMD &&
            report[14] == g_switch_wait_ack_id) {
            g_switch_subcmd_ack_count++;
            switch_init_advance();
        }
    }
}

static void switch_pro_init_task(void) {
    if (!g_host_hid_mounted ||
        !is_switch_pro_controller(g_host_vid, g_host_pid)) {
        return;
    }

    uint64_t now_us = time_us_64();

    if (g_switch_init_step == SWITCH_INIT_IDLE) {
        return;
    }

    if (g_switch_init_step == SWITCH_INIT_FAILED) {
        if (now_us >= g_switch_next_init_us) {
            begin_switch_init();
        }

        return;
    }

    if (g_switch_output_pending && now_us >= g_switch_output_deadline_us) {
        g_switch_output_pending = false;
        g_switch_out_complete_timeout_count++;
    }

    if (g_switch_output_pending) {
        return;
    }

    if (g_switch_wait_ack_kind != SWITCH_ACK_NONE) {
        if (now_us < g_switch_wait_deadline_us) {
            return;
        }

        g_switch_init_timeout_count++;

        if (g_switch_init_retry_count < switch_init_max_retries(g_switch_init_step)) {
            g_switch_init_retry_count++;
            g_switch_wait_ack_kind = SWITCH_ACK_NONE;
            g_switch_wait_ack_id = 0;
            g_switch_next_init_us = now_us + SWITCH_INIT_RETRY_DELAY_US;
        } else {
            switch_init_fail_or_continue();
        }

        return;
    }

    if (now_us < g_switch_next_init_us) {
        return;
    }

    bool sent = false;
    uint8_t wait_kind = SWITCH_ACK_NONE;
    uint8_t wait_id = 0;

    switch (g_switch_init_step) {
        case SWITCH_INIT_USB_HANDSHAKE_1:
            sent = switch_send_usb_cmd(JC_USB_CMD_HANDSHAKE);
            wait_kind = SWITCH_ACK_USB;
            wait_id = JC_USB_CMD_HANDSHAKE;
            break;

        case SWITCH_INIT_USB_BAUDRATE:
            sent = switch_send_usb_cmd(JC_USB_CMD_BAUDRATE_3M);
            wait_kind = SWITCH_ACK_USB;
            wait_id = JC_USB_CMD_BAUDRATE_3M;
            break;

        case SWITCH_INIT_USB_HANDSHAKE_2:
            sent = switch_send_usb_cmd(JC_USB_CMD_HANDSHAKE);
            wait_kind = SWITCH_ACK_USB;
            wait_id = JC_USB_CMD_HANDSHAKE;
            break;

        case SWITCH_INIT_USB_NO_TIMEOUT:
            sent = switch_send_usb_cmd(JC_USB_CMD_NO_TIMEOUT);
            wait_kind = SWITCH_ACK_NONE;
            break;

        case SWITCH_INIT_REQ_DEV_INFO:
            sent = switch_send_subcmd_data(JC_SUBCMD_REQ_DEV_INFO, NULL, 0);
            wait_kind = SWITCH_ACK_SUBCMD;
            wait_id = JC_SUBCMD_REQ_DEV_INFO;
            break;

        case SWITCH_INIT_SET_REPORT_MODE:
            sent = switch_send_subcmd(JC_SUBCMD_SET_REPORT_MODE, JC_INPUT_IMU_DATA);
            wait_kind = SWITCH_ACK_SUBCMD;
            wait_id = JC_SUBCMD_SET_REPORT_MODE;
            break;

        default:
            switch_init_fail_or_continue();
            return;
    }

    if (!sent) {
        g_switch_next_init_us = now_us + SWITCH_INIT_RETRY_DELAY_US;
        return;
    }

    if (wait_kind == SWITCH_ACK_NONE) {
        switch_init_advance();
        g_switch_next_init_us = now_us + SWITCH_INIT_NO_RESPONSE_DELAY_US;
    } else {
        switch_init_wait_for_ack(wait_kind, wait_id);
    }
}

// ============================================================
// USB host on Core 1
// ============================================================

void core1_main(void) {
    sleep_ms(10);

#if PICO_FIRMWARE_MAPPER
    multicore_lockout_victim_init();
#endif

    pio_usb_configuration_t pio_cfg = PIO_USB_DEFAULT_CONFIG;
    pio_cfg.pin_dp = PIO_USB_DP_PIN;

    tuh_configure(1, TUH_CFGID_RPI_PIO_USB_CONFIGURATION, &pio_cfg);
    tuh_init(1);
    g_host_stack_started = true;

    while (true) {
        tuh_task();
        host_rescan_task();
        switch_pro_init_task();
    }
}

// ============================================================
// Main loop
// ============================================================

int main(void) {
    set_sys_clock_khz(120000, true);

    stdio_init_all();

    sleep_ms(50);

    critical_section_init(&g_latest_report_lock);
    critical_section_init(&g_mapper_input_lock);
    mapper_protocol_init();
    mapper_action_init();
#if PICO_FIRMWARE_MAPPER
    g_mapper_profile =
        (mapper_profile_t)mapper_config_get()->settings.active_profile;
    g_mapper_output_enabled = mapper_action_output_enabled();
#endif


    multicore_reset_core1();
    multicore_launch_core1(core1_main);

    tud_init(0);

    absolute_time_t next_report_time = get_absolute_time();
#if !PICO_FIRMWARE_MAPPER || MAPPER_ENABLE_CDC_STATUS
    absolute_time_t next_hello_time = get_absolute_time();
#endif

    while (true) {
        tud_task();
#if PICO_FIRMWARE_MAPPER && !MAPPER_ENABLE_CDC_STATUS
        mapper_protocol_task();
#endif

#if PICO_FIRMWARE_MAPPER
        pico_button_task(time_us_64());
        right_calibration_task(time_us_64());
#endif
#if !PICO_FIRMWARE_MAPPER || MAPPER_ENABLE_CDC_STATUS
        cdc_command_task();
        capture_task();

        if (absolute_time_diff_us(get_absolute_time(), next_hello_time) <= 0) {
            next_hello_time = delayed_by_ms(next_hello_time, 1000);

            char line[768];
            uint64_t now_us = time_us_64();
            bool input_fresh = gamepad_input_is_fresh(NULL);
            uint8_t dp_level = gpio_get(PIO_USB_DP_PIN);
            uint8_t dm_level = gpio_get(PIO_USB_DP_PIN + 1);
            root_port_t *root = PIO_USB_ROOT_PORT(0);
            port_pin_status_t line_state = pio_usb_bus_get_line_state(root);

            snprintf(
                line,
                sizeof(line),
                "HOST GP%u/GP%u dp=%u dm=%u line=%s rinit=%u rconn=%u rfs=%u rsusp=%u rints=%08lX started=%u usb=%u mounts=%lu rescans=%lu hid=%u inst=%u hid_mounts=%lu reports=%lu other=%lu valid=%u fresh=%u sw_step=%u retry=%u wait=%u:%02X usb_ack=%02X/%02X sub_ack=%02X:%02X out=%lu ep=%lu sent=%lu ctrl=%lu ctrl_done=%lu out_to=%lu last=%04X:%04X proto=%s req_fail=%lu sw_fail=%lu sw_to=%lu sw_init_fail=%lu\r\n",
                PIO_USB_DP_PIN,
                PIO_USB_DP_PIN + 1,
                dp_level,
                dm_level,
                line_state_name(line_state),
                root->initialized ? 1 : 0,
                root->connected ? 1 : 0,
                root->is_fullspeed ? 1 : 0,
                root->suspended ? 1 : 0,
                (unsigned long)root->ints,
                g_host_stack_started ? 1 : 0,
                g_host_device_mounted ? 1 : 0,
                (unsigned long)g_host_mount_count,
                (unsigned long)g_host_rescan_count,
                g_host_hid_mounted ? 1 : 0,
                g_host_hid_instance,
                (unsigned long)g_host_hid_mount_count,
                (unsigned long)g_host_hid_report_count,
                (unsigned long)g_host_hid_other_report_count,
                g_gamepad_valid ? 1 : 0,
                input_fresh ? 1 : 0,
                g_switch_init_step,
                g_switch_init_retry_count,
                g_switch_wait_ack_kind,
                g_switch_wait_ack_id,
                g_switch_last_usb_ack_1,
                g_switch_last_usb_ack_3,
                g_switch_last_subcmd_ack,
                g_switch_last_subcmd_id,
                (unsigned long)g_switch_out_submit_count,
                (unsigned long)g_switch_out_ep_submit_count,
                (unsigned long)g_switch_out_sent_count,
                (unsigned long)g_switch_out_ctrl_submit_count,
                (unsigned long)g_switch_out_ctrl_done_count,
                (unsigned long)g_switch_out_complete_timeout_count,
                g_host_vid,
                g_host_pid,
                hid_protocol_name(g_host_hid_protocol),
                (unsigned long)g_host_report_request_fail_count,
                (unsigned long)g_switch_init_send_fail_count,
                (unsigned long)g_switch_init_timeout_count,
                (unsigned long)g_switch_init_fail_count
            );

            cdc_printf_raw(line);
        }
#endif

        absolute_time_t now_time = get_absolute_time();
        int64_t diff_us = absolute_time_diff_us(now_time, next_report_time);

        if (diff_us <= 0) {
            if (hid_any_ready()) {
                uint64_t now_us = time_us_64();
                bool report_queued = false;

#if PICO_FIRMWARE_MAPPER
                g_mapper_profile = (mapper_profile_t)
                    mapper_config_get()->settings.active_profile;
                g_mapper_output_enabled = mapper_action_output_enabled();
                g_mapper_release_pending = mapper_action_release_pending();
                if (!g_mapper_output_enabled || g_mapper_release_pending) {
                    report_queued = send_keyboard_neutral_if_needed();
                    bool keyboard_neutral = mapper_keyboard_is_neutral();
                    report_queued = mapper_action_send_neutral_step(
                                        now_us, keyboard_neutral) ||
                                    report_queued;
                    g_mapper_release_pending = mapper_action_release_pending();
                    next_report_time = delayed_by_us(
                        report_queued ? get_absolute_time() : now_time,
                        KEYMOUSE_REPORT_INTERVAL_US);
                    continue;
                }
#endif

                bool input_fresh = gamepad_input_is_fresh(NULL);

                if (!input_fresh) {
#if PICO_FIRMWARE_MAPPER
                    bool holding_mouse_button =
                        mapper_action_last_mouse_buttons() != 0;
                    bool hold_stale_mouse = false;

                    if (holding_mouse_button) {
                        if (g_stale_mouse_release_deadline_us == 0) {
                            const mapper_config_payload_t *config =
                                mapper_config_get();
                            uint64_t stale_grace_us = (uint64_t)
                                config->settings.mouse_release_grace_ms * 1000u;
                            g_stale_mouse_release_deadline_us =
                                now_us + stale_grace_us;
                        }
                        hold_stale_mouse =
                            now_us < g_stale_mouse_release_deadline_us;
                    }

                    if (hold_stale_mouse) {
                        report_queued = send_keyboard_neutral_if_needed();
                        report_queued = mapper_action_send_stale_mouse_hold(
                                            now_us) ||
                                        report_queued;
                    } else {
                        mapper_action_reset();
                        if (g_gamepad_valid) {
                            clear_gamepad_state();
                        }

                        report_queued = send_keyboard_neutral_if_needed();
                        report_queued = mapper_action_send_neutral_step(
                                            now_us,
                                            mapper_keyboard_is_neutral()) ||
                                        report_queued;
                        g_mapper_release_pending =
                            mapper_action_release_pending();
                    }
#else
                    if (g_gamepad_valid) {
                        clear_gamepad_state();
                    }

                    if (g_last_key_mask != 0) {
                        report_queued = send_keyboard_mask(0);
                        if (report_queued) {
                            g_last_key_mask = 0;
                        }
                    }
#endif

#if !PICO_FIRMWARE_MAPPER
                    if (g_last_mouse_buttons != 0) {
                        report_queued = send_mouse_neutral_report(now_us) || report_queued;
                    }

                    if (!report_queued) {
                        g_mouse_accum_x = 0.0f;
                        g_mouse_accum_y = 0.0f;
                        g_last_mouse_report_us = 0;
                    }
#endif

                    if (report_queued) {
                        next_report_time = delayed_by_us(get_absolute_time(), KEYMOUSE_REPORT_INTERVAL_US);
                    } else {
                        next_report_time = delayed_by_us(now_time, KEYMOUSE_REPORT_INTERVAL_US);
                    }

                    continue;
                }

                g_stale_mouse_release_deadline_us = 0;

#if PICO_FIRMWARE_MAPPER
                uint8_t keycode[6] = {0, 0, 0, 0, 0, 0};
                uint8_t modifier = build_mapper_keycodes(keycode, now_us);
                report_queued = send_keyboard_keycodes_if_changed(modifier, keycode);
                mapper_action_note_keyboard_state(now_us, g_last_modifier,
                                                  g_last_keycode);
                report_queued = send_mouse_report_at_output_rate(now_us) || report_queued;
#else
                uint8_t key_mask = left_stick_to_wasd(g_lx, g_ly);

                if (key_mask != g_last_key_mask) {
                    report_queued = send_keyboard_mask(key_mask);
                    if (report_queued) {
                        g_last_key_mask = key_mask;
                    }
                }

                report_queued = send_mouse_report_at_output_rate(now_us) || report_queued;
#endif

                if (report_queued) {
                    next_report_time = delayed_by_us(get_absolute_time(), KEYMOUSE_REPORT_INTERVAL_US);
                }
            }
        }
    }

    return 0;
}

// ============================================================
// TinyUSB host callbacks
// ============================================================

void tuh_mount_cb(uint8_t dev_addr) {
    uint16_t vid = 0;
    uint16_t pid = 0;

    tuh_vid_pid_get(dev_addr, &vid, &pid);

    g_host_device_mounted = true;
    g_host_mount_count++;
    g_host_dev_addr = dev_addr;
    g_host_vid = vid;
    g_host_pid = pid;
}

void tuh_umount_cb(uint8_t dev_addr) {
    (void)dev_addr;

    clear_gamepad_state();

    g_host_device_mounted = false;
    g_host_hid_mounted = false;
    g_host_dev_addr = 0;
    g_host_hid_instance = 0;
    g_host_hid_protocol = 0;
    g_host_vid = 0;
    g_host_pid = 0;

    g_switch_centered = false;
    reset_switch_init_state();
}

void tuh_hid_mount_cb(
    uint8_t dev_addr,
    uint8_t instance,
    uint8_t const *desc_report,
    uint16_t desc_len
) {
    uint16_t vid = 0;
    uint16_t pid = 0;
    uint8_t const protocol = tuh_hid_interface_protocol(dev_addr, instance);

    tuh_vid_pid_get(dev_addr, &vid, &pid);

    g_host_device_mounted = true;
    g_host_hid_mount_count++;

    bool use_as_active = !g_host_hid_mounted;

    if (is_switch_pro_controller(vid, pid)) {
        use_as_active = !g_host_hid_mounted || instance == 0;
    }

    if (use_as_active) {
        g_host_hid_mounted = true;
        g_host_dev_addr = dev_addr;
        g_host_hid_instance = instance;
        g_host_hid_protocol = protocol;
        g_host_vid = vid;
        g_host_pid = pid;

        if (is_switch_pro_controller(vid, pid)) {
            clear_gamepad_state();
            begin_switch_init();
        }
    }

    (void)desc_report;
    (void)desc_len;

    if (!tuh_hid_receive_report(dev_addr, instance)) {
        g_host_report_request_fail_count++;
    }
}

void tuh_hid_umount_cb(uint8_t dev_addr, uint8_t instance) {
#if !PICO_FIRMWARE_MAPPER || MAPPER_ENABLE_CDC_STATUS
    char line[128];
#endif

    if (report_is_from_active_hid(dev_addr, instance)) {
        clear_gamepad_state();
        g_host_hid_mounted = false;
        g_host_hid_instance = 0;
        g_host_hid_protocol = 0;
        g_switch_centered = false;
        reset_switch_init_state();
    }

#if !PICO_FIRMWARE_MAPPER || MAPPER_ENABLE_CDC_STATUS
    snprintf(
        line,
        sizeof(line),
        "HID unmounted: dev_addr=%u instance=%u\r\n",
        dev_addr,
        instance
    );

    cdc_printf_raw(line);
#endif
}

void tuh_hid_report_received_cb(
    uint8_t dev_addr,
    uint8_t instance,
    uint8_t const *report,
    uint16_t len
) {
    if (report_is_from_active_hid(dev_addr, instance)) {
        record_latest_report(dev_addr, instance, report, len);
        switch_handle_init_report(report, len);
        process_gamepad_report(report, len);
    } else {
        g_host_hid_other_report_count++;
    }

    if (!tuh_hid_receive_report(dev_addr, instance)) {
        g_host_report_request_fail_count++;
    }
}

void tuh_hid_report_sent_cb(
    uint8_t dev_addr,
    uint8_t instance,
    uint8_t const *report,
    uint16_t len
) {
    if (report_is_from_active_hid(dev_addr, instance)) {
        g_switch_out_sent_count++;
        g_switch_output_pending = false;
    }

    (void)report;
    (void)len;
}

void tuh_hid_set_report_complete_cb(
    uint8_t dev_addr,
    uint8_t instance,
    uint8_t report_id,
    uint8_t report_type,
    uint16_t len
) {
    if (report_is_from_active_hid(dev_addr, instance)) {
        g_switch_out_ctrl_done_count++;
        g_switch_output_pending = false;

        if (len == 0) {
            g_switch_out_ctrl_fail_count++;
        }
    }

    (void)report_id;
    (void)report_type;
}

// ============================================================
// TinyUSB device callbacks
// ============================================================

void tud_hid_report_complete_cb(
    uint8_t instance,
    uint8_t const *report,
    uint16_t len
) {
    (void)instance;
    (void)report;
    (void)len;
}

uint16_t tud_hid_get_report_cb(
    uint8_t instance,
    uint8_t report_id,
    hid_report_type_t report_type,
    uint8_t *buffer,
    uint16_t reqlen
) {
    (void)instance;
    (void)report_id;
    (void)report_type;
    (void)buffer;
    (void)reqlen;

    return 0;
}

void tud_hid_set_report_cb(
    uint8_t instance,
    uint8_t report_id,
    hid_report_type_t report_type,
    uint8_t const *buffer,
    uint16_t bufsize
) {
    (void)instance;
    (void)report_id;
    (void)report_type;
    (void)buffer;
    (void)bufsize;
}
