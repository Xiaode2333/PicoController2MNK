#include "mapper_config.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "tusb.h"

static mapper_config_payload_t g_config;
static mapper_config_payload_t g_defaults;

uint16_t mapper_config_virtual_dpi(const mapper_config_payload_t *config) {
    if (config == NULL) {
        return MAPPER_VIRTUAL_DPI_DEFAULT;
    }

    uint16_t dpi = (uint16_t)config->macros[0].reserved[0] |
                   ((uint16_t)config->macros[0].reserved[1] << 8u);
    return dpi == 0u ? MAPPER_VIRTUAL_DPI_DEFAULT : dpi;
}

void mapper_config_set_virtual_dpi(mapper_config_payload_t *config, uint16_t dpi) {
    if (config == NULL) {
        return;
    }

    config->macros[0].reserved[0] = (uint8_t)(dpi & 0xFFu);
    config->macros[0].reserved[1] = (uint8_t)(dpi >> 8u);
}

static void config_set_action(mapper_action_t *action, uint8_t type,
                             uint8_t param1, uint8_t param2) {
    memset(action, 0, sizeof(*action));
    action->type = type;
    action->param1 = param1;
    action->param2 = param2;
}

static void config_set_tap_hold(mapper_action_t bindings[MAPPER_GESTURE_COUNT],
                                uint8_t tap_key, uint8_t hold_key) {
    config_set_action(&bindings[MAPPER_GESTURE_TAP], MAPPER_ACTION_KEY, tap_key, 0);
    config_set_action(&bindings[MAPPER_GESTURE_HOLD], MAPPER_ACTION_KEY, hold_key, 0);
}
static void config_set_continuous_key(mapper_action_t bindings[MAPPER_GESTURE_COUNT],
                                      uint8_t key) {
    config_set_action(&bindings[MAPPER_GESTURE_TAP], MAPPER_ACTION_NONE, 0, 0);
    config_set_action(&bindings[MAPPER_GESTURE_HOLD], MAPPER_ACTION_KEY, key, 0);
    bindings[MAPPER_GESTURE_HOLD].duration_ms = 1; /* immediate while pressed */
}


static void config_set_key(mapper_action_t bindings[MAPPER_GESTURE_COUNT],
                           uint8_t key) {
    config_set_continuous_key(bindings, key);
}

static void config_set_mouse(mapper_action_t bindings[MAPPER_GESTURE_COUNT],
                             uint8_t mouse_buttons) {
    config_set_action(&bindings[MAPPER_GESTURE_TAP], MAPPER_ACTION_NONE, 0, 0);
    config_set_action(&bindings[MAPPER_GESTURE_HOLD], MAPPER_ACTION_MOUSE_BUTTON, mouse_buttons, 0);
    bindings[MAPPER_GESTURE_HOLD].duration_ms = 1; /* immediate while pressed */
}

static void config_set_modifier(mapper_action_t bindings[MAPPER_GESTURE_COUNT],
                                uint8_t modifier) {
    config_set_action(&bindings[MAPPER_GESTURE_TAP], MAPPER_ACTION_NONE, 0, 0);
    config_set_action(&bindings[MAPPER_GESTURE_HOLD], MAPPER_ACTION_MODIFIER_KEY, modifier, 0);
    bindings[MAPPER_GESTURE_HOLD].duration_ms = 1; /* immediate while pressed */
}

static void config_set_wheel(mapper_action_t bindings[MAPPER_GESTURE_COUNT],
                             uint8_t action_type) {
    config_set_action(&bindings[MAPPER_GESTURE_HOLD], action_type, 0, 0);
    bindings[MAPPER_GESTURE_HOLD].duration_ms = 1; /* immediate while pressed */
}

static void config_set_combo(mapper_combo_t *combo, uint8_t profile_mask,
                             uint32_t source_mask, uint32_t suppress_sources,
                             uint8_t action_type, uint8_t param1, uint8_t param2) {
    memset(combo, 0, sizeof(*combo));
    combo->profile_mask = profile_mask;
    combo->source_mask = source_mask;
    combo->suppress_sources = suppress_sources;
    combo->action.type = action_type;
    combo->action.param1 = param1;
    combo->action.param2 = param2;
}

static void config_set_macro_keyboard_step(mapper_macro_step_t *step,
                                           uint8_t modifier,
                                           uint16_t duration_ms) {
    memset(step, 0, sizeof(*step));
    step->type = MAPPER_MACRO_STEP_KEYBOARD;
    step->modifier = modifier;
    step->duration_ms = duration_ms;
}

static void config_set_macro_mouse_step(mapper_macro_step_t *step,
                                        uint8_t mouse_buttons,
                                        uint16_t duration_ms) {
    memset(step, 0, sizeof(*step));
    step->type = MAPPER_MACRO_STEP_MOUSE;
    step->key[0] = mouse_buttons;
    step->duration_ms = duration_ms;
}

static void config_set_documented_macros(mapper_config_payload_t *defaults) {
    for (uint8_t i = 0; i < MAPPER_MACRO_MAX; i++) {
        mapper_macro_t *macro = &defaults->macros[i];
        snprintf(macro->name, sizeof(macro->name), "Macro %u",
                 (unsigned int)i + 1u);
        macro->trigger_mode = MAPPER_MACRO_TRIGGER_PRESS;
    }

    mapper_macro_t *snapshot = &defaults->macros[0];
    snprintf(snapshot->name, sizeof(snapshot->name), "Snapshot Alt+RMB");
    snapshot->step_count = 4;
    config_set_macro_keyboard_step(&snapshot->steps[0], MAPPER_MOD_LEFTALT, 30);
    config_set_macro_mouse_step(&snapshot->steps[1], MAPPER_MOUSE_RIGHT, 10);
    config_set_macro_mouse_step(&snapshot->steps[2], 0, 30);
    config_set_macro_keyboard_step(&snapshot->steps[3], 0, 1);
}

uint32_t mapper_config_crc32(const uint8_t *data, uint32_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (uint32_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (uint32_t bit = 0; bit < 8; bit++) {
            uint32_t mask = (uint32_t)(-(int32_t)(crc & 1u));
            crc = (crc >> 1u) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

static bool action_valid(const mapper_action_t *action) {
    if (action->type > MAPPER_ACTION_SNAPSHOT_MACRO) {
        return false;
    }
    if (action->type == MAPPER_ACTION_MACRO && action->param1 >= MAPPER_MACRO_MAX) {
        return false;
    }
    if (action->type == MAPPER_ACTION_MOUSE_BUTTON &&
        (action->param1 & ~(MAPPER_MOUSE_LEFT | MAPPER_MOUSE_RIGHT | MAPPER_MOUSE_MIDDLE))) {
        return false;
    }
    return true;
}

static bool macro_valid(const mapper_macro_t *macro) {
    if (macro->step_count > MAPPER_MACRO_STEP_MAX) {
        return false;
    }
    if (macro->trigger_mode > MAPPER_MACRO_TRIGGER_TOGGLE) {
        return false;
    }
    for (uint8_t i = 0; i < macro->step_count; i++) {
        if (macro->steps[i].type > MAPPER_MACRO_STEP_MOUSE) {
            return false;
        }
        if (macro->steps[i].type == MAPPER_MACRO_STEP_MOUSE &&
            (macro->steps[i].key[0] &
             ~(MAPPER_MOUSE_LEFT | MAPPER_MOUSE_RIGHT | MAPPER_MOUSE_MIDDLE))) {
            return false;
        }
    }
    return true;
}

static bool config_valid(const mapper_config_payload_t *cfg) {
    const mapper_settings_t *settings = &cfg->settings;
    uint16_t virtual_dpi = mapper_config_virtual_dpi(cfg);

    if (settings->active_profile >= MAPPER_PROFILE_COUNT ||
        settings->output_enabled > 1u ||
        settings->advanced_stick_version > MAPPER_ADVANCED_STICK_VERSION ||
        settings->profile2_accel_enabled > 1u ||
        (settings->advanced_stick_version == MAPPER_ADVANCED_STICK_VERSION &&
         (settings->profile2_outer_threshold_percent < 1u ||
          settings->profile2_outer_threshold_percent > 100u)) ||
        settings->tap_duration_ms < 1u || settings->tap_duration_ms > 60000u ||
        settings->hold_threshold_ms < 1u || settings->hold_threshold_ms > 60000u ||
        settings->double_click_ms < 1u || settings->double_click_ms > 60000u ||
        settings->wheel_turbo_hz < 1u || settings->wheel_turbo_hz > 1000u ||
        settings->wheel_combo_hz < 1u || settings->wheel_combo_hz > 1000u ||
        settings->mouse_release_grace_ms > 5000u ||
        !isfinite(settings->left_deadzone) ||
        !isfinite(settings->right_deadzone) ||
        settings->left_deadzone < 0.0f || settings->left_deadzone >= 1.0f ||
        settings->right_deadzone < 0.0f || settings->right_deadzone >= 1.0f ||
        settings->right_center_x > 4095u || settings->right_center_y > 4095u ||
        virtual_dpi < MAPPER_VIRTUAL_DPI_MIN ||
        virtual_dpi > MAPPER_VIRTUAL_DPI_MAX) {
        return false;
    }
    for (uint8_t p = 0; p < MAPPER_PROFILE_COUNT; p++) {
        if (cfg->settings.left_stick_mode[p] > 2u) {
            return false;
        }
        for (uint8_t s = 0; s < MAPPER_SOURCE_COUNT; s++) {
            for (uint8_t g = 0; g < MAPPER_GESTURE_COUNT; g++) {
                if (!action_valid(&cfg->bindings[p][s][g])) {
                    return false;
                }
            }
        }
    }

    for (uint8_t c = 0; c < MAPPER_COMBO_MAX; c++) {
        const mapper_combo_t *combo = &cfg->combos[c];
        if (!action_valid(&combo->action)) {
            return false;
        }
        if ((combo->profile_mask & ~((1u << MAPPER_PROFILE_COUNT) - 1u)) != 0u) {
            return false;
        }
        if ((combo->source_mask & ~((1u << MAPPER_SOURCE_COUNT) - 1u)) != 0u) {
            return false;
        }
        if ((combo->suppress_sources & ~((1u << MAPPER_SOURCE_COUNT) - 1u)) != 0u) {
            return false;
        }
    }

    for (uint8_t m = 0; m < MAPPER_MACRO_MAX; m++) {
        if (!macro_valid(&cfg->macros[m])) {
            return false;
        }
    }

    return true;
}

bool mapper_config_validate(void) {
    return config_valid(&g_config);
}

mapper_config_payload_t *mapper_config_get(void) {
    return &g_config;
}

static mapper_config_payload_t g_candidate;

bool mapper_config_payload_valid(const uint8_t *payload) {
    if (payload == NULL) {
        return false;
    }
    memcpy(&g_candidate, payload, sizeof(g_candidate));
    return config_valid(&g_candidate);
}

bool mapper_config_apply_payload(const uint8_t *payload) {
    if (!mapper_config_payload_valid(payload)) {
        return false;
    }
    memcpy(&g_config, &g_candidate, sizeof(g_config));
    return true;
}

void mapper_config_factory_reset(void) {
    memcpy(&g_config, &g_defaults, sizeof(g_config));
}

void mapper_config_init_defaults(void) {
    memset(&g_config, 0, sizeof(g_config));
    memset(&g_defaults, 0, sizeof(g_defaults));

    mapper_settings_t *s = &g_defaults.settings;
    s->left_stick_mode[0] = 2;
    s->left_stick_mode[1] = 1;
    s->left_stick_mode[2] = 2;
    s->active_profile = 0;
    s->output_enabled = 1;
    s->advanced_stick_version = MAPPER_ADVANCED_STICK_VERSION;
    s->tap_duration_ms = 40;
    s->hold_threshold_ms = 200;
    s->double_click_ms = 250;
    s->wheel_turbo_hz = 30;
    s->wheel_combo_hz = 10;
    s->mouse_release_grace_ms = 40;
    s->left_deadzone = 0.10f;
    s->right_deadzone = 0.06f;
    s->mouse_speed_x[0] = 5000;
    s->mouse_speed_y[0] = 5000;
    s->mouse_speed_x[1] = 5000;
    s->mouse_speed_y[1] = 4166;
    s->mouse_speed_x[2] = 5000;
    s->mouse_speed_y[2] = 5000;
    s->right_center_x = 2048;
    s->right_center_y = 2048;
    s->profile2_accel_enabled = 1;
    s->profile2_outer_threshold_percent = 95;

    mapper_profile2_stick_t *p2 = &g_defaults.profile2_stick;
    p2->rb_speed_x = 3750;
    p2->rb_speed_y = 2000;
    p2->no_rb_ramp_ms = 300;
    p2->no_rb_extra_x = 4583;
    p2->rb_delay_ms = 250;
    p2->rb_ramp_ms = 1000;
    p2->rb_extra_x = 625;
    p2->rb_extra_y = 625;

    mapper_action_t (*b)[MAPPER_SOURCE_COUNT][MAPPER_GESTURE_COUNT] = g_defaults.bindings;

#define SRC(src) MAPPER_SRC_##src
#define P(src) b[0][SRC(src)]
#define BIND(src) b[0][SRC(src)]

    /* Profile 1 */
    config_set_tap_hold(BIND(DPAD_UP), HID_KEY_5, HID_KEY_G);
    config_set_tap_hold(BIND(DPAD_DOWN), HID_KEY_3, HID_KEY_4);
    config_set_key(BIND(DPAD_LEFT), HID_KEY_B);
    config_set_key(BIND(DPAD_RIGHT), HID_KEY_GRAVE);
    config_set_mouse(BIND(LB), MAPPER_MOUSE_RIGHT);
    config_set_mouse(BIND(RB), MAPPER_MOUSE_LEFT);
    config_set_key(BIND(LT), HID_KEY_Q);
    config_set_key(BIND(RT), HID_KEY_E);
    config_set_tap_hold(BIND(X), HID_KEY_R, HID_KEY_F);
    config_set_key(BIND(A), HID_KEY_SPACE);
    config_set_tap_hold(BIND(B), HID_KEY_C, HID_KEY_Z);
    config_set_mouse(BIND(Y), MAPPER_MOUSE_MIDDLE);
    config_set_modifier(BIND(L3), MAPPER_MOD_LEFTSHIFT);
    config_set_action(&BIND(R3)[MAPPER_GESTURE_TAP], MAPPER_ACTION_ALT_TAP_KEY, 0, 0);
    config_set_action(&BIND(R3)[MAPPER_GESTURE_HOLD], MAPPER_ACTION_KEY, HID_KEY_X, 0);
    config_set_key(BIND(MENU), HID_KEY_TAB);
    config_set_action(&BIND(SNAPSHOT)[MAPPER_GESTURE_TAP], MAPPER_ACTION_MACRO, 0, 0);
    config_set_tap_hold(BIND(OPTION), HID_KEY_M, HID_KEY_ESCAPE);

    /* Profile 2 */
    config_set_key(b[1][SRC(DPAD_UP)], HID_KEY_G);
    config_set_key(b[1][SRC(DPAD_RIGHT)], HID_KEY_4);
    config_set_wheel(b[1][SRC(DPAD_DOWN)], MAPPER_ACTION_WHEEL_UP_TURBO);
    config_set_key(b[1][SRC(DPAD_LEFT)], HID_KEY_B);
    config_set_mouse(b[1][SRC(LB)], MAPPER_MOUSE_RIGHT);
    config_set_mouse(b[1][SRC(RB)], MAPPER_MOUSE_LEFT);
    config_set_modifier(b[1][SRC(LT)], MAPPER_MOD_LEFTCTRL);
    config_set_key(b[1][SRC(RT)], HID_KEY_SPACE);
    config_set_tap_hold(b[1][SRC(X)], HID_KEY_R, HID_KEY_E);
    config_set_key(b[1][SRC(A)], HID_KEY_V);
    config_set_wheel(b[1][SRC(B)], MAPPER_ACTION_WHEEL_DOWN_TURBO);
    config_set_mouse(b[1][SRC(Y)], MAPPER_MOUSE_MIDDLE);
    config_set_key(b[1][SRC(L3)], HID_KEY_Q);
    config_set_action(&b[1][SRC(R3)][MAPPER_GESTURE_TAP], MAPPER_ACTION_ALT_TAP_KEY, 0, 0);
    config_set_action(&b[1][SRC(R3)][MAPPER_GESTURE_HOLD], MAPPER_ACTION_KEY, HID_KEY_3, 0);
    config_set_key(b[1][SRC(MENU)], HID_KEY_TAB);
    config_set_action(&b[1][SRC(SNAPSHOT)][MAPPER_GESTURE_TAP], MAPPER_ACTION_MACRO, 0, 0);
    config_set_tap_hold(b[1][SRC(OPTION)], HID_KEY_ESCAPE, HID_KEY_M);

    /* Profile 3 */
    config_set_key(b[2][SRC(DPAD_UP)], HID_KEY_L);
    config_set_key(b[2][SRC(DPAD_RIGHT)], HID_KEY_5);
    config_set_key(b[2][SRC(DPAD_DOWN)], HID_KEY_H);
    config_set_key(b[2][SRC(DPAD_LEFT)], HID_KEY_B);
    config_set_mouse(b[2][SRC(LB)], MAPPER_MOUSE_RIGHT);
    config_set_mouse(b[2][SRC(RB)], MAPPER_MOUSE_LEFT);
    config_set_key(b[2][SRC(LT)], HID_KEY_V);
    config_set_key(b[2][SRC(RT)], HID_KEY_G);
    config_set_action(&b[2][SRC(X)][MAPPER_GESTURE_TAP], MAPPER_ACTION_KEY, HID_KEY_R, 0);
    config_set_action(&b[2][SRC(X)][MAPPER_GESTURE_DOUBLE], MAPPER_ACTION_KEY, HID_KEY_F, 0);
    config_set_key(b[2][SRC(A)], HID_KEY_SPACE);
    config_set_tap_hold(b[2][SRC(B)], HID_KEY_C, HID_KEY_Z);
    config_set_mouse(b[2][SRC(Y)], MAPPER_MOUSE_MIDDLE);
    config_set_modifier(b[2][SRC(L3)], MAPPER_MOD_LEFTSHIFT);
    config_set_action(&b[2][SRC(R3)][MAPPER_GESTURE_TAP], MAPPER_ACTION_ALT_TAP_KEY, 0, 0);
    config_set_action(&b[2][SRC(R3)][MAPPER_GESTURE_HOLD], MAPPER_ACTION_KEY, HID_KEY_X, 0);
    config_set_key(b[2][SRC(MENU)], HID_KEY_TAB);
    config_set_action(&b[2][SRC(SNAPSHOT)][MAPPER_GESTURE_TAP], MAPPER_ACTION_MACRO, 0, 0);
    config_set_tap_hold(b[2][SRC(OPTION)], HID_KEY_M, HID_KEY_ESCAPE);

    mapper_combo_t *combos = g_defaults.combos;
    const uint32_t face_x = 1u << SRC(X);
    const uint32_t face_y = 1u << SRC(Y);
    const uint32_t face_a = 1u << SRC(A);
    const uint32_t face_b = 1u << SRC(B);
    const uint32_t lt = 1u << SRC(LT);
    const uint32_t rt = 1u << SRC(RT);
    const uint32_t lb = 1u << SRC(LB);
    const uint32_t dpup = 1u << SRC(DPAD_UP);
    const uint32_t dpdown = 1u << SRC(DPAD_DOWN);
    const uint32_t dpleft = 1u << SRC(DPAD_LEFT);
    const uint32_t dpright = 1u << SRC(DPAD_RIGHT);
    const uint32_t l3 = 1u << SRC(L3);
    const uint8_t p12 = 0x03;
    const uint8_t pall = 0x07;

    config_set_combo(&combos[0], p12, lt | rt | face_x, lt | rt | face_x,
                     MAPPER_ACTION_MODIFIER_KEY, MAPPER_MOD_LEFTCTRL, HID_KEY_1);
    config_set_combo(&combos[1], p12, lt | rt | face_y, lt | rt | face_y,
                     MAPPER_ACTION_MODIFIER_KEY, MAPPER_MOD_LEFTCTRL, HID_KEY_2);
    config_set_combo(&combos[2], p12, lt | rt | face_a, lt | rt | face_a,
                     MAPPER_ACTION_MODIFIER_KEY, MAPPER_MOD_LEFTCTRL, HID_KEY_3);
    config_set_combo(&combos[3], p12, lt | rt | face_b, lt | rt | face_b,
                     MAPPER_ACTION_MODIFIER_KEY, MAPPER_MOD_LEFTCTRL, HID_KEY_4);
    config_set_combo(&combos[4], pall, lt | rt | dpup, lt | rt | dpup,
                     MAPPER_ACTION_WHEEL_UP_COMBO, 0, 0);
    config_set_combo(&combos[5], pall, lt | rt | dpdown, lt | rt | dpdown,
                     MAPPER_ACTION_WHEEL_DOWN_COMBO, 0, 0);
    config_set_combo(&combos[6], 0x01, lt | rt | dpleft, lt | rt | dpleft,
                     MAPPER_ACTION_KEY, HID_KEY_F4, 0);
    config_set_combo(&combos[7], 0x01, lt | rt | dpright, lt | rt | dpright,
                     MAPPER_ACTION_KEY, HID_KEY_H, 0);
    config_set_combo(&combos[8], 0x02, l3 | face_y, l3 | face_y,
                     MAPPER_ACTION_KEY, HID_KEY_Z, 0);
    config_set_combo(&combos[9], 0x02, lb | face_b, face_b,
                     MAPPER_ACTION_MODIFIER_KEY, MAPPER_MOD_LEFTSHIFT, 0);
    config_set_combo(&combos[10], 0x02, lb | dpdown, dpdown,
                     MAPPER_ACTION_KEY, HID_KEY_H, 0);
    config_set_combo(&combos[11], 0x04, lt | rt, lt | rt,
                     MAPPER_ACTION_KEY, HID_KEY_X, 0);
    config_set_combo(&combos[12], 0x04, lb | face_b, face_b,
                     MAPPER_ACTION_KEY, HID_KEY_U, 0);
    config_set_combo(&combos[13], 0x04, lb | lt, lt,
                     MAPPER_ACTION_KEY, HID_KEY_Q, 0);
    config_set_combo(&combos[14], 0x04, lb | rt, rt,
                     MAPPER_ACTION_KEY, HID_KEY_E, 0);

    config_set_documented_macros(&g_defaults);
    mapper_config_set_virtual_dpi(&g_defaults, MAPPER_VIRTUAL_DPI_DEFAULT);

    memcpy(&g_config, &g_defaults, sizeof(g_config));

#undef SRC
#undef P
#undef BIND
}

/* Initialize defaults only once; flash-store load may overwrite afterwards. */
static bool g_config_initialized = false;

void mapper_config_ensure_defaults(void) {
    if (!g_config_initialized) {
        mapper_config_init_defaults();
        g_config_initialized = true;
    }
}
