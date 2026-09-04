#include "mapper_action.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "pico/stdlib.h"
#include "tusb.h"

#include "mapper_store.h"

#ifndef MAPPER_TRACE_MOUSE_OUTPUT
#define MAPPER_TRACE_MOUSE_OUTPUT 0
#endif

#if MAPPER_TRACE_MOUSE_OUTPUT
extern void mapper_trace_mouse_output(
    char const *source,
    uint64_t now_us,
    uint8_t previous_buttons,
    uint8_t mouse_buttons,
    uint32_t input_buttons
);
#endif

/* Controller button bits, duplicated here so the action engine does not
 * depend on private main.c definitions. These match Switch Pro reports. */
#define MBTN_Y          0x000001u
#define MBTN_X          0x000002u
#define MBTN_B          0x000004u
#define MBTN_A          0x000008u
#define MBTN_RB         0x000040u
#define MBTN_RT         0x000080u
#define MBTN_MENU       0x000100u
#define MBTN_OPTION     0x000200u
#define MBTN_RSTICK     0x000400u
#define MBTN_LSTICK     0x000800u
#define MBTN_SNAPSHOT   0x002000u
#define MBTN_DPAD_DOWN  0x010000u
#define MBTN_DPAD_UP    0x020000u
#define MBTN_DPAD_RIGHT 0x040000u
#define MBTN_DPAD_LEFT  0x080000u
#define MBTN_LB         0x400000u
#define MBTN_LT         0x800000u

#define SNAPSHOT_ALT_TO_RIGHT_DOWN_US 30000u
#define SNAPSHOT_RIGHT_UP_US 40000u
#define SNAPSHOT_TOTAL_US 70000u

#define MAPPER_HID_MOUSE_INSTANCE 1u
#define GESTURE_PULSE_QUEUE_LEN 16u
#define GESTURE_RELEASE_GAP_US 1000u

typedef struct {
    uint8_t pressed;
    uint8_t hold_active;
    uint8_t double_active;
    uint8_t waiting_double;
    uint8_t tap_kind; /* 0 none, 1 single, 2 double */
    uint8_t pulse_queue[GESTURE_PULSE_QUEUE_LEN];
    uint8_t pulse_queue_head;
    uint8_t pulse_queue_count;
    uint64_t press_time_us;
    uint64_t double_deadline_us;
    uint64_t tap_until_us;
    uint64_t pulse_release_until_us;
} source_state_t;

typedef struct {
    uint8_t modifier;
    uint8_t keycode[6];
    uint8_t count;
} keyboard_builder_t;

typedef struct {
    bool active;
    bool macro_toggle_latched;
    uint8_t alt_pending_key;
    uint8_t alt_next_key;
    uint64_t wheel_next_us;
} action_runtime_t;

static source_state_t g_source_states[MAPPER_SOURCE_COUNT];
static action_runtime_t
    g_binding_runtimes[MAPPER_SOURCE_COUNT][MAPPER_GESTURE_COUNT];
static action_runtime_t g_combo_runtimes[MAPPER_COMBO_MAX];
static bool g_source_suppressed_until_release[MAPPER_SOURCE_COUNT];
static uint8_t g_last_profile = 0xff;
static bool g_neutral_pending = false;
static uint32_t g_suppressed_sources = 0;
static bool g_calibration_active = false;

/* Mouse accumulator and last-sent report are owned by the action engine. */
static float g_mouse_accum_x = 0.0f;
static float g_mouse_accum_y = 0.0f;
static uint64_t g_last_mouse_report_us = 0;
static uint8_t g_last_mouse_buttons = 0;
static int8_t g_last_mouse_dx = 0;
static int8_t g_last_mouse_dy = 0;
static int8_t g_last_mouse_wheel = 0;

static uint8_t g_mouse_buttons_builder = 0;
static int16_t g_wheel_pending = 0;

static uint64_t g_mouse_left_release_deadline_us = 0;
static uint64_t g_mouse_right_release_deadline_us = 0;
static uint64_t g_mouse_middle_release_deadline_us = 0;
static uint8_t g_mouse_forced_release_mask = 0;

/* Profile 2 right-stick outer acceleration (preserves MAPPINGS.md behavior). */
static bool g_profile2_outer_active = false;
static bool g_profile2_outer_rb = false;
static uint64_t g_profile2_outer_start_us = 0;

/* Snapshot macro */
static uint64_t g_snapshot_start_us = 0;
static bool g_snapshot_active = false;

/* Macro playback */
static bool g_macro_active = false;
static uint8_t g_macro_index = 0;
static uint8_t g_macro_step = 0;
static uint64_t g_macro_next_step_us = 0;
static uint64_t g_macro_step_duration_us = 0;
static bool g_macro_needs_neutral = false;
static bool g_macro_keyboard_neutral_done = false;
static bool g_macro_mouse_neutral_done = false;
static bool g_macro_keyboard_dirty = false;
static bool g_macro_mouse_dirty = false;
static action_runtime_t *g_macro_origin_runtime = NULL;

static uint8_t g_macro_key_modifier = 0;
static uint8_t g_macro_keycode[6] = {0, 0, 0, 0, 0, 0};
static uint8_t g_macro_mouse_buttons = 0;
static int8_t g_macro_mouse_dx = 0;
static int8_t g_macro_mouse_dy = 0;
static int8_t g_macro_mouse_wheel = 0;

static float clampf(float value, float lo, float hi) {
    if (value < lo) return lo;
    if (value > hi) return hi;
    return value;
}

static int clamp_int32(int value, int lo, int hi) {
    if (value < lo) return lo;
    if (value > hi) return hi;
    return value;
}

static float apply_deadzone(float value, float deadzone) {
    float magnitude = fabsf(value);
    if (magnitude < deadzone) return 0.0f;
    float sign = value >= 0.0f ? 1.0f : -1.0f;
    return sign * ((magnitude - deadzone) / (1.0f - deadzone));
}

static bool mouse_button_down_with_release_grace(
    uint8_t desired_buttons,
    uint8_t button_mask,
    bool force_release,
    uint64_t now_us,
    uint64_t grace_us,
    uint64_t *release_deadline_us
) {
    if ((desired_buttons & button_mask) != 0) {
        *release_deadline_us = now_us + grace_us;
        return true;
    }

    /* Combo suppression is an intentional cancellation, not a dropped input
     * report. It must bypass the signal-loss grace window. */
    if (force_release) {
        *release_deadline_us = 0;
        return false;
    }

    if ((g_last_mouse_buttons & button_mask) != 0 &&
        *release_deadline_us != 0 &&
        now_us < *release_deadline_us) {
        return true;
    }

    *release_deadline_us = 0;
    return false;
}

static uint8_t live_mouse_buttons_with_release_grace(uint64_t now_us) {
    const mapper_config_payload_t *config = mapper_config_get();
    uint64_t grace_us =
        (uint64_t)config->settings.mouse_release_grace_ms * 1000u;
    uint8_t desired_buttons = g_mouse_buttons_builder;
    uint8_t buttons = 0;

    if (mouse_button_down_with_release_grace(
            desired_buttons, MAPPER_MOUSE_LEFT,
            (g_mouse_forced_release_mask & MAPPER_MOUSE_LEFT) != 0,
            now_us, grace_us,
            &g_mouse_left_release_deadline_us)) {
        buttons |= MAPPER_MOUSE_LEFT;
    }
    if (mouse_button_down_with_release_grace(
            desired_buttons, MAPPER_MOUSE_RIGHT,
            (g_mouse_forced_release_mask & MAPPER_MOUSE_RIGHT) != 0,
            now_us, grace_us,
            &g_mouse_right_release_deadline_us)) {
        buttons |= MAPPER_MOUSE_RIGHT;
    }
    if (mouse_button_down_with_release_grace(
            desired_buttons, MAPPER_MOUSE_MIDDLE,
            (g_mouse_forced_release_mask & MAPPER_MOUSE_MIDDLE) != 0,
            now_us, grace_us,
            &g_mouse_middle_release_deadline_us)) {
        buttons |= MAPPER_MOUSE_MIDDLE;
    }

    return buttons;
}

static void reset_mouse_release_grace(void) {
    g_mouse_left_release_deadline_us = 0;
    g_mouse_right_release_deadline_us = 0;
    g_mouse_middle_release_deadline_us = 0;
    g_mouse_forced_release_mask = 0;
}

static uint32_t source_button_mask(mapper_source_t source) {
    switch (source) {
        case MAPPER_SRC_A: return MBTN_A;
        case MAPPER_SRC_B: return MBTN_B;
        case MAPPER_SRC_X: return MBTN_X;
        case MAPPER_SRC_Y: return MBTN_Y;
        case MAPPER_SRC_LB: return MBTN_LB;
        case MAPPER_SRC_RB: return MBTN_RB;
        case MAPPER_SRC_LT: return MBTN_LT;
        case MAPPER_SRC_RT: return MBTN_RT;
        case MAPPER_SRC_L3: return MBTN_LSTICK;
        case MAPPER_SRC_R3: return MBTN_RSTICK;
        case MAPPER_SRC_DPAD_UP: return MBTN_DPAD_UP;
        case MAPPER_SRC_DPAD_DOWN: return MBTN_DPAD_DOWN;
        case MAPPER_SRC_DPAD_LEFT: return MBTN_DPAD_LEFT;
        case MAPPER_SRC_DPAD_RIGHT: return MBTN_DPAD_RIGHT;
        case MAPPER_SRC_MENU: return MBTN_MENU;
        case MAPPER_SRC_OPTION: return MBTN_OPTION;
        case MAPPER_SRC_SNAPSHOT: return MBTN_SNAPSHOT;
        default: return 0;
    }
}

static bool source_is_pressed(mapper_source_t source, const mapper_input_state_t *state) {
    uint32_t mask = source_button_mask(source);
    if (mask != 0) {
        return (state->buttons & mask) != 0;
    }

    switch (source) {
        case MAPPER_SRC_LSTICK_UP:
            return state->ly < -0.5f && fabsf(state->ly) >= fabsf(state->lx);
        case MAPPER_SRC_LSTICK_DOWN:
            return state->ly > 0.5f && fabsf(state->ly) >= fabsf(state->lx);
        case MAPPER_SRC_LSTICK_LEFT:
            return state->lx < -0.5f && fabsf(state->lx) >= fabsf(state->ly);
        case MAPPER_SRC_LSTICK_RIGHT:
            return state->lx > 0.5f && fabsf(state->lx) >= fabsf(state->ly);
        case MAPPER_SRC_RSTICK_UP:
            return state->ry < -0.5f && fabsf(state->ry) >= fabsf(state->rx);
        case MAPPER_SRC_RSTICK_DOWN:
            return state->ry > 0.5f && fabsf(state->ry) >= fabsf(state->rx);
        case MAPPER_SRC_RSTICK_LEFT:
            return state->rx < -0.5f && fabsf(state->rx) >= fabsf(state->ry);
        case MAPPER_SRC_RSTICK_RIGHT:
            return state->rx > 0.5f && fabsf(state->rx) >= fabsf(state->ry);
        default:
            return false;
    }
}

static bool mask_sources_pressed(uint32_t source_mask, const mapper_input_state_t *state) {
    for (uint32_t i = 0; i < MAPPER_SOURCE_COUNT; i++) {
        if ((source_mask & (1u << i)) != 0 &&
            !source_is_pressed((mapper_source_t)i, state)) {
            return false;
        }
    }
    return source_mask != 0;
}

static void builder_add_keycode(keyboard_builder_t *builder, uint8_t key) {
    if (key == 0) return;
    for (uint8_t i = 0; i < builder->count; i++) {
        if (builder->keycode[i] == key) return;
    }
    if (builder->count < 6) {
        builder->keycode[builder->count++] = key;
    }
}

static void reset_source_states(void) {
    memset(g_source_states, 0, sizeof(g_source_states));
    memset(g_binding_runtimes, 0, sizeof(g_binding_runtimes));
    memset(g_combo_runtimes, 0, sizeof(g_combo_runtimes));
    memset(g_source_suppressed_until_release, 0,
           sizeof(g_source_suppressed_until_release));
    g_suppressed_sources = 0;
    g_mouse_forced_release_mask = 0;
    g_snapshot_active = false;
    g_snapshot_start_us = 0;
}

static void macro_stop(bool request_neutral) {
    g_macro_active = false;
    g_macro_step = 0;
    g_macro_next_step_us = 0;
    g_macro_step_duration_us = 0;
    g_macro_origin_runtime = NULL;
    g_macro_keyboard_dirty = false;
    g_macro_mouse_dirty = false;
    g_macro_key_modifier = 0;
    memset(g_macro_keycode, 0, sizeof(g_macro_keycode));
    g_macro_mouse_buttons = 0;
    g_macro_mouse_dx = 0;
    g_macro_mouse_dy = 0;
    g_macro_mouse_wheel = 0;
    g_macro_needs_neutral = request_neutral;
    g_macro_keyboard_neutral_done = !request_neutral;
    g_macro_mouse_neutral_done = !request_neutral;
}

static void macro_start(uint8_t index, action_runtime_t *origin,
                        uint64_t now_us, bool repeating) {
    const mapper_config_payload_t *config = mapper_config_get();
    if (index >= MAPPER_MACRO_MAX) return;
    if (config->macros[index].step_count == 0) return;

    if (!repeating && g_macro_active && g_macro_origin_runtime != NULL) {
        g_macro_origin_runtime->macro_toggle_latched = false;
    }
    macro_stop(false);
    g_macro_active = true;
    g_macro_index = index;
    g_macro_step = 0;
    g_macro_next_step_us = now_us;
    g_macro_origin_runtime = origin;
    g_macro_needs_neutral = false;
}

static void macro_task(uint64_t now_us) {
    if (!g_macro_active) return;
    if (g_macro_keyboard_dirty || g_macro_mouse_dirty) return;

    const mapper_macro_t *macro = &mapper_config_get()->macros[g_macro_index];

    while (g_macro_active) {
        if (g_macro_step >= macro->step_count) {
            bool repeat = false;
            if (g_macro_origin_runtime != NULL) {
                if (macro->trigger_mode == MAPPER_MACRO_TRIGGER_WHILE_HELD) {
                    repeat = g_macro_origin_runtime->active;
                } else if (macro->trigger_mode == MAPPER_MACRO_TRIGGER_TOGGLE) {
                    repeat = g_macro_origin_runtime->macro_toggle_latched;
                }
            }

            if (repeat) {
                uint8_t index = g_macro_index;
                action_runtime_t *origin = g_macro_origin_runtime;
                macro_start(index, origin, now_us, true);
                macro = &mapper_config_get()->macros[g_macro_index];
                continue;
            }

            macro_stop(true);
            return;
        }

        if (now_us < g_macro_next_step_us) return;

        const mapper_macro_step_t *step = &macro->steps[g_macro_step];

        if (step->type == MAPPER_MACRO_STEP_DELAY) {
            /* Delay is a timing operation; both device states stay held. */
        } else if (step->type == MAPPER_MACRO_STEP_KEYBOARD) {
            g_macro_key_modifier = step->modifier;
            memcpy(g_macro_keycode, step->key, sizeof(g_macro_keycode));
            g_macro_keyboard_dirty = true;
        } else if (step->type == MAPPER_MACRO_STEP_MOUSE) {
            g_macro_mouse_buttons = step->key[0];
            g_macro_mouse_dx = (int8_t)step->key[1];
            g_macro_mouse_dy = (int8_t)step->key[2];
            g_macro_mouse_wheel = step->value;
            g_macro_mouse_dirty = true;
        }

        uint32_t duration_ms = step->duration_ms;
        if (duration_ms < 1) duration_ms = 1;
        uint64_t duration_us = (uint64_t)duration_ms * 1000u;
        if (g_macro_keyboard_dirty || g_macro_mouse_dirty) {
            /* Start dwell only after this device state reaches its endpoint. */
            g_macro_step_duration_us = duration_us;
            g_macro_next_step_us = 0;
        } else {
            g_macro_step_duration_us = 0;
            g_macro_next_step_us = now_us + duration_us;
        }
        g_macro_step++;

        if (g_macro_keyboard_dirty || g_macro_mouse_dirty) return;
    }
}

static void macro_step_delivered(uint64_t now_us) {
    if (!g_macro_active || g_macro_step_duration_us == 0) return;
    g_macro_next_step_us = now_us + g_macro_step_duration_us;
    g_macro_step_duration_us = 0;
}

static void out_add_wheel(action_runtime_t *runtime, uint8_t action_type,
                          bool active, uint64_t now_us) {
    const mapper_config_payload_t *config = mapper_config_get();
    bool up = action_type == MAPPER_ACTION_WHEEL_UP_TURBO ||
              action_type == MAPPER_ACTION_WHEEL_UP_COMBO;
    uint32_t hz;

    if (action_type == MAPPER_ACTION_WHEEL_UP_TURBO ||
        action_type == MAPPER_ACTION_WHEEL_DOWN_TURBO) {
        hz = config->settings.wheel_turbo_hz;
    } else {
        hz = config->settings.wheel_combo_hz;
    }
    if (hz < 1) hz = 1;
    if (hz > 1000) hz = 1000;

    uint64_t interval_us = 1000000u / hz;

    if (!active) {
        runtime->wheel_next_us = 0;
        return;
    }

    if (runtime->wheel_next_us == 0 || now_us >= runtime->wheel_next_us) {
        int32_t delta = up ? 1 : -1;
        g_wheel_pending = (int16_t)clamp_int32((int32_t)g_wheel_pending + delta, -127, 127);
        runtime->wheel_next_us = now_us + interval_us;
    }
}

static void clear_toggle_latches_except(action_runtime_t *keep) {
    for (uint8_t source = 0; source < MAPPER_SOURCE_COUNT; source++) {
        for (uint8_t gesture = 0; gesture < MAPPER_GESTURE_COUNT; gesture++) {
            action_runtime_t *runtime = &g_binding_runtimes[source][gesture];
            if (runtime != keep) runtime->macro_toggle_latched = false;
        }
    }
    for (uint8_t combo = 0; combo < MAPPER_COMBO_MAX; combo++) {
        action_runtime_t *runtime = &g_combo_runtimes[combo];
        if (runtime != keep) runtime->macro_toggle_latched = false;
    }
}

static void macro_touch_edge(uint8_t index, action_runtime_t *runtime,
                             bool active, bool was_active,
                             uint64_t now_us) {
    if (index >= MAPPER_MACRO_MAX) return;

    const mapper_macro_t *macro = &mapper_config_get()->macros[index];
    if (active && !was_active) {
        if (macro->trigger_mode == MAPPER_MACRO_TRIGGER_TOGGLE) {
            if (runtime->macro_toggle_latched) {
                runtime->macro_toggle_latched = false;
                if (g_macro_active && g_macro_origin_runtime == runtime) {
                    macro_stop(true);
                }
            } else {
                clear_toggle_latches_except(runtime);
                runtime->macro_toggle_latched = true;
                macro_start(index, runtime, now_us, false);
            }
        } else if (macro->trigger_mode != MAPPER_MACRO_TRIGGER_RELEASE) {
            macro_start(index, runtime, now_us, false);
        }
    } else if (!active && was_active) {
        if (macro->trigger_mode == MAPPER_MACRO_TRIGGER_RELEASE) {
            macro_start(index, runtime, now_us, false);
        }
    }
}

static void apply_action(const mapper_action_t *action,
                         action_runtime_t *runtime, bool active,
                         uint64_t now_us,
                         keyboard_builder_t *keyboard) {
    bool was_active = runtime->active;

    switch (action->type) {
        case MAPPER_ACTION_NONE:
            break;

        case MAPPER_ACTION_KEY:
            if (active) builder_add_keycode(keyboard, action->param1);
            break;

        case MAPPER_ACTION_MODIFIER_KEY:
            if (active) {
                keyboard->modifier |= action->param1;
                builder_add_keycode(keyboard, action->param2);
            }
            break;

        case MAPPER_ACTION_MOUSE_BUTTON:
            if (active) g_mouse_buttons_builder |= action->param1;
            break;

        case MAPPER_ACTION_WHEEL_UP_TURBO:
        case MAPPER_ACTION_WHEEL_DOWN_TURBO:
        case MAPPER_ACTION_WHEEL_UP_COMBO:
        case MAPPER_ACTION_WHEEL_DOWN_COMBO:
            out_add_wheel(runtime, action->type, active, now_us);
            break;

        case MAPPER_ACTION_MACRO:
            macro_touch_edge(action->param1, runtime, active, was_active,
                             now_us);
            break;

        case MAPPER_ACTION_ALT_TAP_KEY:
            if (active && !was_active) {
                runtime->alt_pending_key = runtime->alt_next_key != 0
                                               ? runtime->alt_next_key
                                               : HID_KEY_1;
                runtime->alt_next_key =
                    runtime->alt_pending_key == HID_KEY_1 ? HID_KEY_2
                                                          : HID_KEY_1;
            }
            if (active) {
                builder_add_keycode(keyboard, runtime->alt_pending_key);
            } else {
                runtime->alt_pending_key = 0;
            }
            break;

        case MAPPER_ACTION_SNAPSHOT_MACRO:
            if (active && !was_active) {
                g_snapshot_active = true;
                g_snapshot_start_us = now_us;
            }
            break;

        default:
            break;
    }

    runtime->active = active;
}

static void cancel_action_runtime(action_runtime_t *runtime) {
    if (runtime->macro_toggle_latched) {
        runtime->macro_toggle_latched = false;
        if (g_macro_active && g_macro_origin_runtime == runtime) {
            macro_stop(true);
        }
    }
    runtime->active = false;
    runtime->alt_pending_key = 0;
    runtime->wheel_next_us = 0;
}

static void cancel_source_state(mapper_source_t source) {
    memset(&g_source_states[source], 0, sizeof(g_source_states[source]));
    for (uint8_t gesture = 0; gesture < MAPPER_GESTURE_COUNT; gesture++) {
        cancel_action_runtime(&g_binding_runtimes[source][gesture]);
    }
}

static bool source_requires_release_latch(mapper_source_t source) {
    const mapper_config_payload_t *config = mapper_config_get();
    uint8_t profile = config->settings.active_profile;
    const mapper_action_t *binding = config->bindings[profile][source];
    return binding[MAPPER_GESTURE_TAP].type != MAPPER_ACTION_NONE ||
           binding[MAPPER_GESTURE_DOUBLE].type != MAPPER_ACTION_NONE;
}

static uint8_t action_mouse_buttons(const mapper_action_t *action) {
    if (action == NULL || action->type != MAPPER_ACTION_MOUSE_BUTTON) {
        return 0;
    }
    return (uint8_t)(action->param1 &
                     (MAPPER_MOUSE_LEFT | MAPPER_MOUSE_RIGHT |
                      MAPPER_MOUSE_MIDDLE));
}

static uint8_t active_source_mouse_buttons(uint8_t profile,
                                           mapper_source_t source) {
    const mapper_config_payload_t *config = mapper_config_get();
    uint8_t buttons = 0;

    for (uint8_t gesture = 0; gesture < MAPPER_GESTURE_COUNT; gesture++) {
        if (g_binding_runtimes[source][gesture].active) {
            buttons |= action_mouse_buttons(
                &config->bindings[profile][source][gesture]);
        }
    }
    return buttons;
}

static void start_gesture_pulse(source_state_t *state, uint8_t kind,
                                uint64_t now_us, uint64_t duration_us) {
    state->tap_kind = kind;
    state->tap_until_us = now_us + duration_us;
    state->pulse_release_until_us = 0;
}

static void queue_gesture_pulse(source_state_t *state, uint8_t kind,
                                uint64_t now_us, uint64_t duration_us) {
    if (kind == 0) return;

    if (state->tap_kind == 0 && state->pulse_release_until_us == 0 &&
        state->pulse_queue_count == 0) {
        start_gesture_pulse(state, kind, now_us, duration_us);
        return;
    }

    if (state->pulse_queue_count < GESTURE_PULSE_QUEUE_LEN) {
        uint8_t tail = (uint8_t)(
            (state->pulse_queue_head + state->pulse_queue_count) %
            GESTURE_PULSE_QUEUE_LEN);
        state->pulse_queue[tail] = kind;
        state->pulse_queue_count++;
    }

}

static void update_gesture_pulse(source_state_t *state, uint64_t now_us,
                                 uint64_t duration_us) {
    if (state->tap_kind != 0 && now_us >= state->tap_until_us) {
        state->tap_kind = 0;
        state->tap_until_us = 0;
        state->pulse_release_until_us = now_us + GESTURE_RELEASE_GAP_US;
    }

    if (state->tap_kind == 0 && state->pulse_release_until_us != 0 &&
        now_us >= state->pulse_release_until_us) {
        state->pulse_release_until_us = 0;
    }

    if (state->tap_kind == 0 && state->pulse_release_until_us == 0 &&
        state->pulse_queue_count != 0) {
        uint8_t kind = state->pulse_queue[state->pulse_queue_head];
        state->pulse_queue_head = (uint8_t)(
            (state->pulse_queue_head + 1u) % GESTURE_PULSE_QUEUE_LEN);
        state->pulse_queue_count--;
        start_gesture_pulse(state, kind, now_us, duration_us);
    }
}

static void process_button_source(mapper_source_t source, bool pressed,
                                  uint64_t now_us,
                                  keyboard_builder_t *keyboard) {
    const mapper_config_payload_t *config = mapper_config_get();
    uint8_t profile = config->settings.active_profile;
    source_state_t *state = &g_source_states[source];
    const mapper_action_t *binding = config->bindings[profile][source];
    bool has_double_action = binding[MAPPER_GESTURE_DOUBLE].type != MAPPER_ACTION_NONE;
    uint64_t pulse_duration_us =
        (uint64_t)config->settings.tap_duration_ms * 1000u;

    update_gesture_pulse(state, now_us, pulse_duration_us);

    if (state->waiting_double && now_us >= state->double_deadline_us) {
        state->waiting_double = false;
        queue_gesture_pulse(state, 1, now_us, pulse_duration_us);
    }

    if (pressed && !state->pressed) {
        state->pressed = true;
        state->press_time_us = now_us;
        state->hold_active = false;
        state->double_active = false;

        if (state->waiting_double && now_us < state->double_deadline_us) {
            state->waiting_double = false;
            state->double_active = true;
            queue_gesture_pulse(state, 2, now_us, pulse_duration_us);
        }
    }

    if (!pressed && state->pressed) {
        bool was_double = state->double_active;
        bool was_hold = state->hold_active;
        state->pressed = false;
        state->hold_active = false;
        state->double_active = false;
        state->press_time_us = 0;

        if (!was_hold && !was_double) {
            if (has_double_action) {
                state->waiting_double = true;
                state->double_deadline_us = now_us + config->settings.double_click_ms * 1000u;
            } else {
                queue_gesture_pulse(state, 1, now_us, pulse_duration_us);
            }
        }
    }

    uint32_t hold_delay_ms = binding[MAPPER_GESTURE_HOLD].duration_ms != 0
                                 ? binding[MAPPER_GESTURE_HOLD].duration_ms
                                 : config->settings.hold_threshold_ms;
    if (binding[MAPPER_GESTURE_HOLD].type != MAPPER_ACTION_NONE &&
        pressed && !state->double_active && !state->hold_active &&
        now_us - state->press_time_us >= (uint64_t)hold_delay_ms * 1000u) {
        state->hold_active = true;
        state->waiting_double = false;
    }

    update_gesture_pulse(state, now_us, pulse_duration_us);
    bool tap_active = state->tap_kind == 1;
    bool double_active = state->tap_kind == 2;

    apply_action(&binding[MAPPER_GESTURE_TAP],
                 &g_binding_runtimes[source][MAPPER_GESTURE_TAP],
                 tap_active, now_us, keyboard);
    apply_action(&binding[MAPPER_GESTURE_HOLD],
                 &g_binding_runtimes[source][MAPPER_GESTURE_HOLD],
                 pressed && state->hold_active, now_us, keyboard);
    apply_action(&binding[MAPPER_GESTURE_DOUBLE],
                 &g_binding_runtimes[source][MAPPER_GESTURE_DOUBLE],
                 double_active, now_us, keyboard);
}

static uint8_t left_stick_wasd_mask(const mapper_input_state_t *state) {
    const mapper_config_payload_t *config = mapper_config_get();
    uint8_t profile = config->settings.active_profile;
    uint8_t mode = config->settings.left_stick_mode[profile];
    float lx = state->lx;
    float ly = state->ly;

    if (sqrtf(lx * lx + ly * ly) < config->settings.left_deadzone) {
        return 0;
    }
    if (mode == 0) return 0;

    uint8_t mask = 0;
    if (mode == 1) {
        if (fabsf(lx) >= fabsf(ly)) {
            mask = lx < 0.0f ? 0x02 : 0x08; /* A/D */
        } else {
            mask = ly < 0.0f ? 0x01 : 0x04; /* W/S */
        }
        return mask;
    }

    float angle = atan2f(ly, lx) * 180.0f / 3.14159265f;
    if (angle < 0.0f) angle += 360.0f;
    if (angle >= 247.5f && angle < 292.5f) mask = 0x01;
    else if (angle >= 292.5f && angle < 337.5f) mask = 0x01 | 0x08;
    else if (angle >= 337.5f || angle < 22.5f) mask = 0x08;
    else if (angle >= 22.5f && angle < 67.5f) mask = 0x04 | 0x08;
    else if (angle >= 67.5f && angle < 112.5f) mask = 0x04;
    else if (angle >= 112.5f && angle < 157.5f) mask = 0x04 | 0x02;
    else if (angle >= 157.5f && angle < 202.5f) mask = 0x02;
    else if (angle >= 202.5f && angle < 247.5f) mask = 0x01 | 0x02;
    return mask;
}

static void add_wasd_keys(keyboard_builder_t *keyboard, uint8_t mask) {
    if (mask & 0x01) builder_add_keycode(keyboard, HID_KEY_W);
    if (mask & 0x02) builder_add_keycode(keyboard, HID_KEY_A);
    if (mask & 0x04) builder_add_keycode(keyboard, HID_KEY_S);
    if (mask & 0x08) builder_add_keycode(keyboard, HID_KEY_D);
}

uint8_t mapper_action_build_keycodes(uint8_t keycode[6], uint64_t now_us) {
    mapper_input_state_t state;
    mapper_input_snapshot(&state);

    const mapper_config_payload_t *config = mapper_config_get();
    uint8_t profile = config->settings.active_profile;

    if (g_last_profile != profile) {
        reset_source_states();
        g_last_profile = profile;
    }

    keyboard_builder_t keyboard;
    memset(&keyboard, 0, sizeof(keyboard));
    g_mouse_buttons_builder = 0;
    g_mouse_forced_release_mask = 0;

    /* Evaluate combos, highest priority = lowest array index. */
    uint32_t suppressed_sources = 0;
    uint32_t claimed_sources = 0;
    for (uint8_t i = 0; i < MAPPER_COMBO_MAX; i++) {
        const mapper_combo_t *combo = &config->combos[i];
        bool profile_enabled =
            (combo->profile_mask & (1u << profile)) != 0;
        bool matched = combo->action.type != MAPPER_ACTION_NONE &&
                       profile_enabled &&
                       mask_sources_pressed(combo->source_mask, &state);

        if (!matched) {
            apply_action(&combo->action, &g_combo_runtimes[i], false,
                         now_us, &keyboard);
            continue;
        }

        if ((combo->source_mask & claimed_sources) != 0) {
            /* A higher-priority overlapping combo owns these sources. */
            if (g_combo_runtimes[i].active) {
                g_mouse_forced_release_mask |=
                    action_mouse_buttons(&combo->action);
            }
            cancel_action_runtime(&g_combo_runtimes[i]);
            continue;
        }

        claimed_sources |= combo->source_mask;
        suppressed_sources |= combo->suppress_sources;
        apply_action(&combo->action, &g_combo_runtimes[i], true,
                     now_us, &keyboard);
    }
    g_suppressed_sources = suppressed_sources;

    /* Left stick is a continuous 8/4-way generator. */
    const uint32_t left_stick_sources =
        (1u << MAPPER_SRC_LSTICK_UP) |
        (1u << MAPPER_SRC_LSTICK_DOWN) |
        (1u << MAPPER_SRC_LSTICK_LEFT) |
        (1u << MAPPER_SRC_LSTICK_RIGHT);
    if ((suppressed_sources & left_stick_sources) == 0) {
        add_wasd_keys(&keyboard, left_stick_wasd_mask(&state));
    }

    /* All advertised sources are bindable. Stick bindings augment the default
     * left-WASD and right-analog generators unless a combo suppresses them. */
    for (uint8_t i = 0; i < MAPPER_SOURCE_COUNT; i++) {
        mapper_source_t source = (mapper_source_t)i;
        bool pressed = source_is_pressed(source, &state);

        if ((suppressed_sources & (1u << i)) != 0) {
            g_mouse_forced_release_mask |=
                active_source_mouse_buttons(profile, source);
            cancel_source_state(source);
            if (pressed && source_requires_release_latch(source)) {
                g_source_suppressed_until_release[i] = true;
            }
            if (!pressed) g_source_suppressed_until_release[i] = false;
            continue;
        }

        if (g_source_suppressed_until_release[i]) {
            g_mouse_forced_release_mask |=
                active_source_mouse_buttons(profile, source);
            cancel_source_state(source);
            if (!pressed) g_source_suppressed_until_release[i] = false;
            continue;
        }

        process_button_source(source, pressed, now_us, &keyboard);
    }

    if (g_snapshot_active) {
        uint64_t elapsed = now_us - g_snapshot_start_us;
        if (elapsed >= SNAPSHOT_TOTAL_US) {
            g_snapshot_active = false;
            g_snapshot_start_us = 0;
        } else {
            keyboard.modifier |= MAPPER_MOD_LEFTALT;
            if (elapsed >= SNAPSHOT_ALT_TO_RIGHT_DOWN_US &&
                elapsed < SNAPSHOT_RIGHT_UP_US) {
                g_mouse_buttons_builder |= MAPPER_MOUSE_RIGHT;
            }
        }
    }

    /* Action edges must keep running during playback so a held/toggle macro
     * can observe release or the next press. Playback owns actual HID output. */
    macro_task(now_us);
    if (g_macro_active) {
        g_wheel_pending = 0;
        memcpy(keycode, g_macro_keycode, 6);
        return g_macro_key_modifier;
    }

    if (g_macro_needs_neutral) {
        memset(keycode, 0, 6);
        return 0;
    }

    memcpy(keycode, keyboard.keycode, 6);
    return keyboard.modifier;
}

static bool mouse_report_matches(uint8_t buttons, int8_t dx, int8_t dy,
                                 int8_t wheel) {
    return buttons == g_last_mouse_buttons &&
           dx == g_last_mouse_dx &&
           dy == g_last_mouse_dy &&
           wheel == g_last_mouse_wheel;
}

static void trace_action_mouse_output(
    char const *source,
    uint64_t now_us,
    uint8_t previous_buttons,
    uint8_t buttons
) {
#if MAPPER_TRACE_MOUSE_OUTPUT
    mapper_input_state_t state;
    mapper_input_snapshot(&state);
    mapper_trace_mouse_output(
        source, now_us, previous_buttons, buttons, state.buttons);
#else
    (void)source;
    (void)now_us;
    (void)previous_buttons;
    (void)buttons;
#endif
}

static bool mouse_report_send(uint64_t now_us, uint8_t buttons, int8_t dx,
                              int8_t dy, int8_t wheel, bool force,
                              char const *source) {
    if (!force && mouse_report_matches(buttons, dx, dy, wheel)) {
        return false;
    }
    if (!tud_hid_n_mouse_report(MAPPER_HID_MOUSE_INSTANCE, 0, buttons, dx, dy, wheel, 0)) {
        return false;
    }
    uint8_t previous_buttons = g_last_mouse_buttons;
    g_last_mouse_buttons = buttons;
    g_last_mouse_dx = dx;
    g_last_mouse_dy = dy;
    g_last_mouse_wheel = wheel;
    g_last_mouse_report_us = now_us;
    trace_action_mouse_output(
        source, now_us, previous_buttons, buttons);
    return true;
}

static void macro_finish_neutral_if_complete(void) {
    if (g_macro_needs_neutral && g_macro_keyboard_neutral_done &&
        g_macro_mouse_neutral_done) {
        g_macro_needs_neutral = false;
    }
}

void mapper_action_note_keyboard_state(uint64_t now_us, uint8_t modifier,
                                       const uint8_t keycode[6]) {
    if (keycode == NULL) return;

    if (g_macro_active && g_macro_keyboard_dirty &&
        modifier == g_macro_key_modifier &&
        memcmp(keycode, g_macro_keycode, sizeof(g_macro_keycode)) == 0) {
        g_macro_keyboard_dirty = false;
        macro_step_delivered(now_us);
    }

    if (g_macro_needs_neutral && modifier == 0) {
        static const uint8_t neutral[6] = {0, 0, 0, 0, 0, 0};
        if (memcmp(keycode, neutral, sizeof(neutral)) == 0) {
            g_macro_keyboard_neutral_done = true;
            macro_finish_neutral_if_complete();
        }
    }
}

bool mapper_action_send_mouse(uint64_t now_us) {
    uint8_t live_mouse_buttons =
        live_mouse_buttons_with_release_grace(now_us);

    if (g_macro_active) {
        bool has_relative = g_macro_mouse_dx != 0 ||
                            g_macro_mouse_dy != 0 ||
                            g_macro_mouse_wheel != 0;
        uint8_t macro_mouse_buttons =
            (uint8_t)(live_mouse_buttons | g_macro_mouse_buttons);
        if (g_macro_mouse_dirty) {
            if (!has_relative &&
                mouse_report_matches(macro_mouse_buttons, 0, 0, 0)) {
                g_macro_mouse_dirty = false;
                macro_step_delivered(now_us);
                return false;
            }

            bool queued = mouse_report_send(
                now_us, macro_mouse_buttons, g_macro_mouse_dx,
                g_macro_mouse_dy, g_macro_mouse_wheel, has_relative,
                "macro");
            if (!queued) return false;

            /* Relative axes and wheel are one-shot events. Keep them dirty
             * until the endpoint accepts the report, then consume exactly once. */
            g_macro_mouse_dx = 0;
            g_macro_mouse_dy = 0;
            g_macro_mouse_wheel = 0;
            g_macro_mouse_dirty = false;
            macro_step_delivered(now_us);
            return true;
        }

        return mouse_report_send(now_us, macro_mouse_buttons, 0, 0, 0,
                                 false, "macro_hold");
    }

    if (g_macro_needs_neutral) {
        g_mouse_accum_x = 0.0f;
        g_mouse_accum_y = 0.0f;
        if (mouse_report_matches(live_mouse_buttons, 0, 0, 0)) {
            g_macro_mouse_neutral_done = true;
            macro_finish_neutral_if_complete();
            return false;
        }

        bool queued = mouse_report_send(
            now_us, live_mouse_buttons, 0, 0, 0, false, "macro_end");
        if (queued) {
            g_macro_mouse_neutral_done = true;
            macro_finish_neutral_if_complete();
        }
        return queued;
    }

    mapper_input_state_t state;
    mapper_input_snapshot(&state);

    const mapper_config_payload_t *config = mapper_config_get();
    uint8_t profile = config->settings.active_profile;

    const uint32_t right_stick_sources =
        (1u << MAPPER_SRC_RSTICK_UP) |
        (1u << MAPPER_SRC_RSTICK_DOWN) |
        (1u << MAPPER_SRC_RSTICK_LEFT) |
        (1u << MAPPER_SRC_RSTICK_RIGHT);
    bool suppress_movement = g_calibration_active ||
                             (g_suppressed_sources & right_stick_sources) != 0;
    float rx = suppress_movement
                   ? 0.0f
                   : apply_deadzone(state.rx, config->settings.right_deadzone);
    float ry = suppress_movement
                   ? 0.0f
                   : apply_deadzone(state.ry, config->settings.right_deadzone);
    if (suppress_movement) {
        g_mouse_accum_x = 0.0f;
        g_mouse_accum_y = 0.0f;
    }

    float speed_x = (float)config->settings.mouse_speed_x[profile];
    float speed_y = (float)config->settings.mouse_speed_y[profile];

    if (profile == 1 && !suppress_movement) {
        bool advanced = config->settings.advanced_stick_version ==
                        MAPPER_ADVANCED_STICK_VERSION;
        bool accel_enabled = advanced ?
            config->settings.profile2_accel_enabled != 0u : true;
        float outer_threshold = advanced ?
            (float)config->settings.profile2_outer_threshold_percent / 100.0f : 0.95f;
        uint16_t rb_speed_x = advanced ? config->profile2_stick.rb_speed_x : 3750u;
        uint16_t rb_speed_y = advanced ? config->profile2_stick.rb_speed_y : 2000u;
        bool rb_held = (state.buttons & MBTN_RB) != 0;
        if (rb_held) {
            speed_x = (float)rb_speed_x;
            speed_y = (float)rb_speed_y;
        }

        float stick_mag = sqrtf(rx * rx + ry * ry);
        if (accel_enabled && stick_mag >= outer_threshold) {
            if (!g_profile2_outer_active || g_profile2_outer_rb != rb_held) {
                g_profile2_outer_active = true;
                g_profile2_outer_rb = rb_held;
                g_profile2_outer_start_us = now_us;
            }

            uint64_t outer_us = now_us - g_profile2_outer_start_us;
            if (rb_held) {
                uint64_t delay_us = advanced ?
                    (uint64_t)config->profile2_stick.rb_delay_ms * 1000u : 250000u;
                uint64_t ramp_us = advanced ?
                    (uint64_t)config->profile2_stick.rb_ramp_ms * 1000u : 1000000u;
                if (outer_us > delay_us) {
                    float accel = ramp_us == 0u ? 1.0f : clampf(
                        (float)(outer_us - delay_us) / (float)ramp_us, 0.0f, 1.0f);
                    float extra_x = advanced ?
                        (float)config->profile2_stick.rb_extra_x : 625.0f;
                    float extra_y = advanced ?
                        (float)config->profile2_stick.rb_extra_y : 625.0f;
                    speed_x += extra_x * accel;
                    speed_y += extra_y * accel;
                }
            } else {
                uint64_t ramp_us = advanced ?
                    (uint64_t)config->profile2_stick.no_rb_ramp_ms * 1000u : 300000u;
                float accel = ramp_us == 0u ? 1.0f :
                    clampf((float)outer_us / (float)ramp_us, 0.0f, 1.0f);
                float extra_x = advanced ?
                    (float)config->profile2_stick.no_rb_extra_x : 4583.0f;
                speed_x += extra_x * accel;
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

    /* USB HID carries relative counts rather than a DPI value. Model virtual
     * DPI by scaling every base/accelerated stick speed around the legacy
     * 1000-DPI behavior. */
    float dpi_scale = (float)mapper_config_virtual_dpi(config) /
                      (float)MAPPER_VIRTUAL_DPI_DEFAULT;
    speed_x *= dpi_scale;
    speed_y *= dpi_scale;

    float dt = 0.000125f; /* 8 kHz nominal output rate */
    if (g_last_mouse_report_us != 0 && now_us > g_last_mouse_report_us) {
        uint64_t elapsed_us = now_us - g_last_mouse_report_us;
        if (elapsed_us < 100000u) {
            dt = (float)elapsed_us / 1000000.0f;
        } else {
            /* A long endpoint/configuration stall is not cursor debt. */
            g_mouse_accum_x = 0.0f;
            g_mouse_accum_y = 0.0f;
        }
    }

    float next_accum_x = g_mouse_accum_x + rx * speed_x * dt;
    float next_accum_y = g_mouse_accum_y + ry * speed_y * dt;
    int whole_x = (int)next_accum_x;
    int whole_y = (int)next_accum_y;
    int move_x = clamp_int32(whole_x, -127, 127);
    int move_y = clamp_int32(whole_y, -127, 127);
    next_accum_x = whole_x == move_x ? next_accum_x - (float)move_x : 0.0f;
    next_accum_y = whole_y == move_y ? next_accum_y - (float)move_y : 0.0f;

    uint8_t buttons = live_mouse_buttons;

    int wheel = clamp_int32(g_wheel_pending, -127, 127);

    if (!tud_hid_n_mouse_report(MAPPER_HID_MOUSE_INSTANCE, 0, (uint8_t)buttons,
                                (int8_t)move_x, (int8_t)move_y,
                                (int8_t)wheel, 0)) {
        return false;
    }

    uint8_t previous_buttons = g_last_mouse_buttons;
    g_mouse_accum_x = next_accum_x;
    g_mouse_accum_y = next_accum_y;
    g_last_mouse_report_us = now_us;
    g_last_mouse_buttons = buttons;
    g_last_mouse_dx = (int8_t)move_x;
    g_last_mouse_dy = (int8_t)move_y;
    g_last_mouse_wheel = (int8_t)wheel;
    g_wheel_pending -= (int16_t)wheel;
    trace_action_mouse_output(
        "normal", now_us, previous_buttons, buttons);
    return true;
}

uint8_t mapper_action_last_mouse_buttons(void) {
    return g_last_mouse_buttons;
}

bool mapper_action_send_stale_mouse_hold(uint64_t now_us) {
    if (g_last_mouse_buttons == 0) {
        return false;
    }

    return mouse_report_send(
        now_us, g_last_mouse_buttons, 0, 0, 0, true, "stale_hold");
}

bool mapper_action_send_neutral_step(uint64_t now_us, bool keyboard_neutral) {
    macro_stop(false);
    g_wheel_pending = 0;
    g_mouse_accum_x = 0.0f;
    g_mouse_accum_y = 0.0f;
    g_mouse_buttons_builder = 0;
    reset_mouse_release_grace();
    g_profile2_outer_active = false;
    g_profile2_outer_rb = false;
    g_profile2_outer_start_us = 0;


    bool queued = false;
    bool has_non_neutral_mouse =
        g_last_mouse_buttons != 0 || g_last_mouse_dx != 0 ||
        g_last_mouse_dy != 0 || g_last_mouse_wheel != 0;
    if (has_non_neutral_mouse) {
        queued = mouse_report_send(
            now_us, 0, 0, 0, 0, false, "neutral");
        if (!queued) {
            g_neutral_pending = true;
            return false;
        }
    }

    g_last_mouse_report_us = now_us;
    g_neutral_pending = !keyboard_neutral;
    return queued;
}

void mapper_action_request_release(void) {
    macro_stop(false);
    reset_source_states();
    g_neutral_pending = true;
    g_mouse_buttons_builder = 0;
    g_mouse_forced_release_mask = 0;
}

bool mapper_action_release_pending(void) {
    return g_neutral_pending;
}

void mapper_action_reset(void) {
    macro_stop(false);
    reset_source_states();
    g_mouse_buttons_builder = 0;
    g_wheel_pending = 0;
    g_mouse_accum_x = 0.0f;
    g_mouse_accum_y = 0.0f;
    reset_mouse_release_grace();
    g_profile2_outer_active = false;
    g_profile2_outer_rb = false;
    g_profile2_outer_start_us = 0;

    g_neutral_pending = true;
}

void mapper_action_cycle_profile(void) {
    mapper_config_payload_t *config = mapper_config_get();
    config->settings.active_profile =
        (uint8_t)((config->settings.active_profile + 1u) % MAPPER_PROFILE_COUNT);
    mapper_action_reset();
}

void mapper_action_toggle_output(void) {
    mapper_config_payload_t *config = mapper_config_get();
    config->settings.output_enabled = config->settings.output_enabled ? 0 : 1;
    mapper_action_reset();
}

bool mapper_action_output_enabled(void) {
    return mapper_config_get()->settings.output_enabled != 0;
}

void mapper_action_set_calibration(uint16_t rx_center, uint16_t ry_center,
                                   float right_deadzone) {
    mapper_config_payload_t *config = mapper_config_get();
    config->settings.right_center_x = rx_center;
    config->settings.right_center_y = ry_center;
    config->settings.right_deadzone = right_deadzone;
    mapper_parser_set_calibration(rx_center, ry_center, right_deadzone);
    mapper_action_reset();
}

void mapper_action_set_calibration_active(bool active) {
    g_calibration_active = active;
    g_mouse_accum_x = 0.0f;
    g_mouse_accum_y = 0.0f;
    g_profile2_outer_active = false;
    g_profile2_outer_rb = false;
    g_profile2_outer_start_us = 0;
    if (active) g_last_mouse_report_us = 0;
}

void mapper_action_init(void) {
    mapper_store_init();
    mapper_parser_set_calibration(mapper_config_get()->settings.right_center_x,
                                  mapper_config_get()->settings.right_center_y,
                                  mapper_config_get()->settings.right_deadzone);
    reset_source_states();
    macro_stop(false);
    g_calibration_active = false;
    g_neutral_pending = false;
}
