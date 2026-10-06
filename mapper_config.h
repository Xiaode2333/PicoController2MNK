#ifndef MAPPER_CONFIG_H
#define MAPPER_CONFIG_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MAPPER_PROFILE_COUNT 3u
#define MAPPER_SOURCE_COUNT 25u
#define MAPPER_GESTURE_COUNT 3u
#define MAPPER_COMBO_MAX 64u
#define MAPPER_MACRO_MAX 8u
#define MAPPER_MACRO_STEP_MAX 64u
#define MAPPER_MACRO_NAME_MAX 24u

/* Payload is intentionally fixed-size so the wire format and flash record
 * format stay stable between firmware and desktop builds. */
#define MAPPER_CONFIG_PAYLOAD_SIZE 8816u
#define MAPPER_CONFIG_LEGACY_PAYLOAD_SIZE 8000u
#define MAPPER_ADVANCED_STICK_VERSION 1u
#define MAPPER_VIRTUAL_DPI_DEFAULT 5000u
#define MAPPER_VIRTUAL_DPI_MIN 100u
#define MAPPER_VIRTUAL_DPI_MAX 20000u
#define MAPPER_MOUSE_MODE_VERSION 1u
#define MAPPER_MOUSE_MODE_SENSITIVITY_MIN 1u
#define MAPPER_MOUSE_MODE_SENSITIVITY_MAX 1000u
#define MAPPER_PROFILE2_AIM_SOURCE_MACRO 6u
#define MAPPER_PROFILE2_AIM_SOURCE_TAG 0x4100u

/* Stable logical input IDs. */
typedef enum {
    MAPPER_SRC_A = 0,
    MAPPER_SRC_B,
    MAPPER_SRC_X,
    MAPPER_SRC_Y,
    MAPPER_SRC_LB,
    MAPPER_SRC_RB,
    MAPPER_SRC_LT,
    MAPPER_SRC_RT,
    MAPPER_SRC_L3,
    MAPPER_SRC_R3,
    MAPPER_SRC_DPAD_UP,
    MAPPER_SRC_DPAD_DOWN,
    MAPPER_SRC_DPAD_LEFT,
    MAPPER_SRC_DPAD_RIGHT,
    MAPPER_SRC_MENU,
    MAPPER_SRC_OPTION,
    MAPPER_SRC_SNAPSHOT,
    MAPPER_SRC_LSTICK_UP,
    MAPPER_SRC_LSTICK_DOWN,
    MAPPER_SRC_LSTICK_LEFT,
    MAPPER_SRC_LSTICK_RIGHT,
    MAPPER_SRC_RSTICK_UP,
    MAPPER_SRC_RSTICK_DOWN,
    MAPPER_SRC_RSTICK_LEFT,
    MAPPER_SRC_RSTICK_RIGHT
} mapper_source_t;

typedef enum {
    MAPPER_GESTURE_TAP = 0,
    MAPPER_GESTURE_HOLD,
    MAPPER_GESTURE_DOUBLE
} mapper_gesture_t;

typedef enum {
    MAPPER_ACTION_NONE = 0,
    MAPPER_ACTION_KEY,
    MAPPER_ACTION_MODIFIER_KEY,
    MAPPER_ACTION_MOUSE_BUTTON,
    MAPPER_ACTION_WHEEL_UP_TURBO,
    MAPPER_ACTION_WHEEL_DOWN_TURBO,
    MAPPER_ACTION_WHEEL_UP_COMBO,
    MAPPER_ACTION_WHEEL_DOWN_COMBO,
    MAPPER_ACTION_MACRO,
    MAPPER_ACTION_ALT_TAP_KEY,
    MAPPER_ACTION_SNAPSHOT_MACRO,
    MAPPER_ACTION_MOUSE_MODE_TOGGLE_KEY,
    MAPPER_ACTION_MOUSE_MODE_SWAP,
    MAPPER_ACTION_TWO_KEYS,
    MAPPER_ACTION_STOP_ALL
} mapper_action_type_t;

/* Tagged modes use a previously ignored byte without changing payload size.
 * Untagged legacy values keep their original behavior. */
#define MAPPER_ACTION_MODE_TOGGLE 0x80u
#define MAPPER_ACTION_MODE_CLICK 0x81u
#define MAPPER_ACTION_MODE_PRESS 0x82u
#define MAPPER_ACTION_MODE_RELEASE 0x83u
#define MAPPER_MACRO_TRIGGER_OVERRIDE 0x80u
#define MAPPER_ACTION_INPUT_TAG 0x4000u
#define MAPPER_ACTION_INPUT_MASK 0x03u
#define MAPPER_INPUT_WHILE_ACTIVE 0u
#define MAPPER_INPUT_PRESSED 1u
#define MAPPER_INPUT_RELEASED 2u
#define MAPPER_INPUT_CLICK 3u

/* Mouse button flags follow the standard HID mouse report bits. */
#define MAPPER_MOUSE_LEFT   0x01u
#define MAPPER_MOUSE_RIGHT  0x02u
#define MAPPER_MOUSE_MIDDLE 0x04u

#define MAPPER_MOD_LEFTCTRL   0x01u
#define MAPPER_MOD_LEFTSHIFT  0x02u
#define MAPPER_MOD_LEFTALT    0x04u
#define MAPPER_MOD_LEFTGUI    0x08u
#define MAPPER_MOD_RIGHTCTRL  0x10u
#define MAPPER_MOD_RIGHTSHIFT 0x20u
#define MAPPER_MOD_RIGHTALT   0x40u
#define MAPPER_MOD_RIGHTGUI   0x80u

typedef struct __attribute__((packed)) {
    uint8_t type;         /* mapper_action_type_t */
    uint8_t param1;       /* keycode, modifier, mouse-button mask or macro index */
    uint8_t param2;       /* second keycode for MODIFIER_KEY/TWO_KEYS actions */
    uint8_t trigger_mode; /* tagged output toggle / per-binding macro trigger override */
    int16_t value;        /* 0x4000 | click_ms<<2 | input_event (0..3), else legacy reserved */
    uint16_t duration_ms; /* optional per-action duration override */
} mapper_action_t;

typedef struct __attribute__((packed)) {
    uint8_t profile_mask;      /* bit0..2 */
    uint32_t source_mask;      /* bit N = (1u << N) */
    uint32_t suppress_sources; /* participants whose normal output is suppressed */
    mapper_action_t action;
} mapper_combo_t;

typedef enum {
    MAPPER_MACRO_STEP_DELAY = 0,
    MAPPER_MACRO_STEP_KEYBOARD = 1,
    MAPPER_MACRO_STEP_MOUSE = 2,
    MAPPER_MACRO_STEP_WHEEL_UP_TURBO = 3,
    MAPPER_MACRO_STEP_WHEEL_DOWN_TURBO = 4,
    MAPPER_MACRO_STEP_WHEEL_UP_COMBO = 5,
    MAPPER_MACRO_STEP_WHEEL_DOWN_COMBO = 6,
    MAPPER_MACRO_STEP_ALT_TAP_KEY = 7,
    MAPPER_MACRO_STEP_MOUSE_MODE_TOGGLE_KEY = 8,
    MAPPER_MACRO_STEP_MOUSE_MODE_SWAP = 9
} mapper_macro_step_type_t;

typedef enum {
    MAPPER_MACRO_TRIGGER_PRESS = 0,
    MAPPER_MACRO_TRIGGER_RELEASE = 1,
    MAPPER_MACRO_TRIGGER_WHILE_HELD = 2,
    MAPPER_MACRO_TRIGGER_TOGGLE = 3
} mapper_macro_trigger_t;

typedef struct __attribute__((packed)) {
    uint8_t type;        /* mapper_macro_step_type_t */
    uint8_t modifier;    /* keyboard modifier for keyboard steps */
    uint8_t key[6];      /* HID keycodes for keyboard steps, otherwise zero */
    int8_t value;        /* mouse dx/dy/wheel/button mask depending on step */
    uint16_t duration_ms;
} mapper_macro_step_t;

typedef struct __attribute__((packed)) {
    char name[MAPPER_MACRO_NAME_MAX];
    uint8_t step_count;
    uint8_t trigger_mode; /* mapper_macro_trigger_t */
    /* Macro 0 stores the global virtual DPI here, little-endian. Keeping the
     * value in these reserved bytes preserves its legacy wire position. */
    uint8_t reserved[2];
    mapper_macro_step_t steps[MAPPER_MACRO_STEP_MAX];
} mapper_macro_t;

typedef struct __attribute__((packed)) {
    uint8_t left_stick_mode[3]; /* 0=off, 1=4-way WASD, 2=8-way WASD */
    uint8_t active_profile;
    uint8_t output_enabled;
    uint8_t advanced_stick_version;
    uint32_t tap_duration_ms;
    uint32_t hold_threshold_ms;
    uint32_t double_click_ms;
    uint32_t wheel_turbo_hz;
    uint32_t wheel_combo_hz;
    uint32_t mouse_release_grace_ms;
    float left_deadzone;
    float right_deadzone;
    uint16_t mouse_speed_x[3];
    uint16_t mouse_speed_y[3];
    uint16_t right_center_x;
    uint16_t right_center_y;
    uint8_t profile2_accel_enabled;
    uint8_t profile2_outer_threshold_percent;
} mapper_settings_t;

typedef struct __attribute__((packed)) {
    /* Legacy wire names: rb_* are ADS values; no_rb_* are hip-fire values.
     * The Aim input is stored separately in macro 6's reserved header bytes. */
    uint16_t rb_speed_x;
    uint16_t rb_speed_y;
    uint16_t no_rb_ramp_ms;
    uint16_t no_rb_extra_x;
    uint16_t rb_delay_ms;
    uint16_t rb_ramp_ms;
    uint16_t rb_extra_x;
    uint16_t rb_extra_y;
} mapper_profile2_stick_t;

typedef struct __attribute__((packed)) {
    mapper_settings_t settings;
    mapper_action_t bindings[MAPPER_PROFILE_COUNT][MAPPER_SOURCE_COUNT][MAPPER_GESTURE_COUNT];
    mapper_combo_t combos[MAPPER_COMBO_MAX];
    mapper_macro_t macros[MAPPER_MACRO_MAX];
    mapper_profile2_stick_t profile2_stick;
} mapper_config_payload_t;

_Static_assert(sizeof(mapper_config_payload_t) == MAPPER_CONFIG_PAYLOAD_SIZE,
               "mapper_config_payload_t must match MAPPER_CONFIG_PAYLOAD_SIZE");

/* Input snapshot supplied by main.c. */
typedef struct {
    uint32_t buttons;
    float lx;
    float ly;
    float rx;
    float ry;
    uint16_t raw_lx;
    uint16_t raw_ly;
    uint16_t raw_rx;
    uint16_t raw_ry;
} mapper_input_state_t;

void mapper_config_init_defaults(void);
void mapper_config_ensure_defaults(void);
void mapper_config_factory_reset(void);
mapper_config_payload_t *mapper_config_get(void);
mapper_source_t mapper_config_profile2_aim_source(const mapper_config_payload_t *config);
void mapper_config_set_profile2_aim_source(mapper_config_payload_t *config,
                                          mapper_source_t source);
uint16_t mapper_config_virtual_dpi(const mapper_config_payload_t *config);
void mapper_config_set_virtual_dpi(mapper_config_payload_t *config, uint16_t dpi);
uint16_t mapper_config_mouse_mode_sensitivity(
    const mapper_config_payload_t *config, uint8_t mode);
float mapper_config_mouse_mode_deadzone(
    const mapper_config_payload_t *config, uint8_t mode);
void mapper_config_set_mouse_modes(mapper_config_payload_t *config,
                                   uint16_t sensitivity_1,
                                   float deadzone_1,
                                   uint16_t sensitivity_2,
                                   float deadzone_2);
void mapper_config_set_mouse_mode_deadzone(mapper_config_payload_t *config,
                                           uint8_t mode, float deadzone);
bool mapper_config_apply_payload(const uint8_t *payload);
bool mapper_config_apply_legacy_payload(const uint8_t *payload);
bool mapper_config_payload_valid(const uint8_t *payload);
bool mapper_config_validate(void);
uint32_t mapper_config_crc32(const uint8_t *data, uint32_t len);

#ifdef __cplusplus
}
#endif

#endif /* MAPPER_CONFIG_H */
