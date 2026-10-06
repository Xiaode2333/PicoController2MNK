/* Exercise actual HID output with physical edges, gestures and macro acks. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "mapper_action.h"
#include "mapper_store.h"

static mapper_input_state_t input;
static uint64_t now_us = 1000000;
static uint8_t keys[6], modifier, mouse_buttons;
static int wheels;
static bool mouse_ready = true;

void mapper_input_snapshot(mapper_input_state_t *state) { *state = input; }
void mapper_parser_set_calibration(uint16_t x, uint16_t y, float deadzone) {
    (void)x; (void)y; (void)deadzone;
}
void mapper_store_init(void) { mapper_config_init_defaults(); }
bool tud_hid_n_mouse_report(uint8_t instance, uint8_t report, uint8_t buttons,
                            int8_t x, int8_t y, int8_t wheel, int8_t pan) {
    (void)instance; (void)report; (void)x; (void)y; (void)pan;
    if (!mouse_ready) return false;
    mouse_buttons = buttons;
    wheels += wheel;
    return true;
}

static void tick(uint32_t buttons, uint32_t elapsed_us) {
    input.buttons = buttons;
    now_us += elapsed_us;
    modifier = mapper_action_build_keycodes(keys, now_us);
    mapper_action_note_keyboard_state(now_us, modifier, keys);
    mapper_action_send_mouse(now_us);
}

static mapper_config_payload_t *prepare(void) {
    mapper_action_init();
    mapper_config_payload_t *cfg = mapper_config_get();
    memset(cfg->bindings, 0, sizeof(cfg->bindings));
    memset(cfg->combos, 0, sizeof(cfg->combos));
    memset(cfg->macros[0].steps, 0, sizeof(cfg->macros[0].steps));
    cfg->settings.active_profile = 0;
    memset(cfg->settings.left_stick_mode, 0, sizeof(cfg->settings.left_stick_mode));
    memset(&input, 0, sizeof(input));
    mouse_ready = true;
    mapper_action_request_release();
    mapper_action_send_neutral_step(++now_us, true);
    tick(0, 1000);
    wheels = 0;
    return cfg;
}

static mapper_action_t output(uint8_t type, uint8_t p1, uint8_t p2) {
    return (mapper_action_t){.type = type, .param1 = p1, .param2 = p2,
        .trigger_mode = MAPPER_ACTION_MODE_TOGGLE, .duration_ms = 1};
}

static void activate(uint32_t buttons) {
    tick(buttons, 1000); tick(buttons, 1000);
}

static void test_outputs(void) {
    const uint8_t types[] = {MAPPER_ACTION_KEY, MAPPER_ACTION_MODIFIER_KEY,
        MAPPER_ACTION_TWO_KEYS, MAPPER_ACTION_MOUSE_BUTTON};
    for (unsigned i = 0; i < sizeof(types); i++) {
        mapper_config_payload_t *cfg = prepare();
        cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD] =
            output(types[i], types[i] == MAPPER_ACTION_MOUSE_BUTTON ? 3 : 4, 5);
        activate(8);
        for (unsigned j = 0; j < 10; j++) tick(8, 1000); /* one flip per edge */
        tick(0, 1000); tick(0, 100000);
        if (types[i] == MAPPER_ACTION_KEY) assert(keys[0] == 4);
        if (types[i] == MAPPER_ACTION_TWO_KEYS) assert(keys[0] == 4 && keys[1] == 5);
        if (types[i] == MAPPER_ACTION_MODIFIER_KEY) assert(modifier == 4 && keys[0] == 5);
        if (types[i] == MAPPER_ACTION_MOUSE_BUTTON) assert(mouse_buttons == 3);
        activate(8);
        assert(keys[0] == 0 && modifier == 0 && mouse_buttons == 0);
        tick(0, 1000);
    }
}

static void test_tap_hold_double_and_wheel(void) {
    mapper_config_payload_t *cfg = prepare();
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_TAP] = output(MAPPER_ACTION_KEY, 4, 0);
    tick(8, 1000); tick(0, 1000); assert(keys[0] == 4);
    tick(0, 50000); tick(8, 1000); tick(0, 1000); assert(keys[0] == 0);

    cfg = prepare();
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_KEY, 4, 0);
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD].duration_ms = 500;
    tick(8, 1000); tick(8, 499000); assert(keys[0] == 0);
    tick(8, 1000); assert(keys[0] == 4);
    tick(0, 1000); assert(keys[0] == 4);

    cfg = prepare();
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_DOUBLE] = output(MAPPER_ACTION_KEY, 4, 0);
    tick(8, 1000); tick(0, 1000); tick(8, 1000); assert(keys[0] == 4);
    tick(0, 1000); tick(0, 50000);
    tick(8, 1000); tick(0, 1000); tick(8, 1000); assert(keys[0] == 0);

    cfg = prepare();
    cfg->settings.wheel_turbo_hz = 10;
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_WHEEL_UP_TURBO, 0, 0);
    activate(8); tick(0, 1000); tick(0, 100000); assert(wheels == 2);
    activate(8); int before = wheels; tick(0, 500000); assert(wheels == before);
}

static void test_combo_and_suppression(void) {
    mapper_config_payload_t *cfg = prepare();
    cfg->combos[0] = (mapper_combo_t){.profile_mask = 1, .source_mask = (1u << MAPPER_SRC_A) | (1u << MAPPER_SRC_B),
        .suppress_sources = (1u << MAPPER_SRC_A), .action = output(MAPPER_ACTION_MOUSE_BUTTON, 2, 0)};
    cfg->combos[0].action.duration_ms = 10;
    tick(12, 1000); tick(12, 9000); assert(mouse_buttons == 0);
    tick(12, 1000); assert(mouse_buttons == 2);
    tick(0, 1000); assert(mouse_buttons == 2);
    tick(12, 1000); tick(12, 10000); assert(mouse_buttons == 0);

    cfg = prepare();
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_MOUSE_BUTTON, 1, 0);
    activate(8); tick(0, 1000); assert(mouse_buttons == 1);
    cfg->combos[0] = (mapper_combo_t){.profile_mask = 1, .source_mask = 3, .suppress_sources = 1};
    cfg->combos[0].action.type = MAPPER_ACTION_KEY;
    cfg->combos[0].action.param1 = 5;
    tick(12, 1000); assert(mouse_buttons == 0);
    tick(8, 1000); tick(8, 100000); assert(mouse_buttons == 0); /* must release A */
    tick(0, 1000); activate(8); assert(mouse_buttons == 1);
}

static void install_macro(mapper_config_payload_t *cfg, uint8_t source, uint8_t trigger) {
    cfg->macros[0].trigger_mode = MAPPER_MACRO_TRIGGER_RELEASE; /* override wins */
    cfg->macros[0].step_count = 2;
    cfg->macros[0].steps[0] = (mapper_macro_step_t){.type = MAPPER_MACRO_STEP_KEYBOARD, .key = {6}, .duration_ms = 10};
    cfg->macros[0].steps[1] = (mapper_macro_step_t){.type = MAPPER_MACRO_STEP_KEYBOARD, .duration_ms = 10};
    cfg->bindings[0][source][MAPPER_GESTURE_HOLD] = (mapper_action_t){.type = MAPPER_ACTION_MACRO,
        .trigger_mode = MAPPER_MACRO_TRIGGER_OVERRIDE | trigger, .duration_ms = 1};
}

static void test_macros_and_stop(void) {
    for (uint8_t mode = 0; mode <= MAPPER_MACRO_TRIGGER_TOGGLE; mode++) {
        mapper_config_payload_t *cfg = prepare();
        install_macro(cfg, MAPPER_SRC_A, mode);
        activate(8);
        if (mode == MAPPER_MACRO_TRIGGER_RELEASE) assert(keys[0] == 0);
        else assert(keys[0] == 6);
        tick(0, 1000);
        if (mode == MAPPER_MACRO_TRIGGER_RELEASE) assert(keys[0] == 6);
        if (mode == MAPPER_MACRO_TRIGGER_WHILE_HELD) assert(keys[0] == 0); /* stop immediately */
        tick(0, 10000); tick(0, 10000); tick(0, 1000);
        if (mode == MAPPER_MACRO_TRIGGER_TOGGLE) {
            assert(keys[0] == 6); /* another cycle */
            activate(8); assert(keys[0] == 0);
        }
    }

    mapper_config_payload_t *cfg = prepare();
    install_macro(cfg, MAPPER_SRC_A, MAPPER_MACRO_TRIGGER_TOGGLE);
    cfg->bindings[0][MAPPER_SRC_B][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_MOUSE_BUTTON, 1, 0);
    cfg->bindings[0][MAPPER_SRC_X][MAPPER_GESTURE_HOLD] = (mapper_action_t){.type = MAPPER_ACTION_STOP_ALL, .duration_ms = 1};
    activate(12); tick(0, 1000); assert(mouse_buttons == 1 && keys[0] == 6);
    activate(2); assert(keys[0] == 0 && mouse_buttons == 0);
    tick(2, 100000); tick(0, 1000); assert(keys[0] == 0 && mouse_buttons == 0);
    activate(12); assert(keys[0] == 6 && mouse_buttons == 1);
}

static void test_reset_and_backpressure(void) {
    for (unsigned kind = 0; kind < 3; kind++) {
        mapper_config_payload_t *cfg = prepare();
        cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_KEY, 4, 0);
        cfg->bindings[0][MAPPER_SRC_B][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_MOUSE_BUTTON, 1, 0);
        activate(12); tick(0, 1000); assert(keys[0] == 4 && mouse_buttons == 1);
        if (kind == 0) mapper_action_request_release(); /* disconnect */
        if (kind == 1) mapper_action_toggle_output();
        if (kind == 2) mapper_action_cycle_profile();
        mapper_action_send_neutral_step(++now_us, true);
        tick(0, 1000); assert(keys[0] == 0 && mouse_buttons == 0);
    }
    mapper_config_payload_t *cfg = prepare();
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_MOUSE_BUTTON, 1, 0);
    activate(8); tick(0, 1000);
    mouse_ready = false; activate(8); assert(mouse_buttons == 1);
    mouse_ready = true; tick(8, 1000); assert(mouse_buttons == 0); /* failed send does not undo flip */
}

static void test_held_alt_survives_macro(void) {
    mapper_config_payload_t *cfg = prepare();
    cfg->combos[0] = (mapper_combo_t){.profile_mask = 1,
        .source_mask = (1u << MAPPER_SRC_LB) | (1u << MAPPER_SRC_RB),
        .action = {.type = MAPPER_ACTION_MODIFIER_KEY, .param1 = MAPPER_MOD_LEFTALT}};
    const uint32_t chord = 0x400040u;
    tick(chord, 1000);
    for (unsigned i = 0; i < 100; i++) { tick(chord, 10000); assert(modifier == MAPPER_MOD_LEFTALT); }
    install_macro(cfg, MAPPER_SRC_A, MAPPER_MACRO_TRIGGER_PRESS);
    activate(chord | 8); assert(modifier == MAPPER_MOD_LEFTALT && keys[0] == 6);
    tick(chord, 10000); assert(modifier == MAPPER_MOD_LEFTALT);
    tick(chord, 10000); assert(modifier == MAPPER_MOD_LEFTALT);
    tick(chord, 1000); assert(modifier == MAPPER_MOD_LEFTALT && keys[0] == 0);
    tick(0, 1000); assert(modifier == 0);
}

static void test_events_clicks_and_explicit_release(void) {
    for (uint8_t event = MAPPER_INPUT_PRESSED; event <= MAPPER_INPUT_CLICK; event++) {
        mapper_config_payload_t *cfg = prepare();
        cfg->combos[0] = (mapper_combo_t){.profile_mask = 1, .source_mask = 3,
            .action = {.type = MAPPER_ACTION_MODIFIER_KEY, .param1 = MAPPER_MOD_LEFTALT,
                       .value = MAPPER_ACTION_INPUT_TAG | (20 << 2) | event}};
        tick(12, 1000);
        assert(modifier == (event == MAPPER_INPUT_PRESSED ? MAPPER_MOD_LEFTALT : 0));
        tick(12, 30000); assert(modifier == 0);
        tick(0, 1000);
        assert(modifier == (event != MAPPER_INPUT_PRESSED ? MAPPER_MOD_LEFTALT : 0));
        tick(0, 20000); assert(modifier == 0);
        if (event == MAPPER_INPUT_CLICK) {
            tick(12, 1000); tick(12, 300000); tick(0, 1000); assert(modifier == 0); /* long hold is not click */
        }
    }
    mapper_config_payload_t *cfg = prepare();
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_MOUSE_BUTTON, 1, 0);
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD].trigger_mode = MAPPER_ACTION_MODE_CLICK;
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD].value = MAPPER_ACTION_INPUT_TAG | (20 << 2);
    mouse_ready = false; activate(8); tick(0, 100000); assert(mouse_buttons == 0);
    mouse_ready = true; tick(0, 1000); assert(mouse_buttons == 1); /* full pulse starts on accepted report */
    tick(0, 19000); assert(mouse_buttons == 1);
    tick(0, 1000); assert(mouse_buttons == 0);

    cfg = prepare();
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_MODIFIER_KEY, MAPPER_MOD_LEFTALT, 0);
    cfg->bindings[0][MAPPER_SRC_A][MAPPER_GESTURE_HOLD].trigger_mode = MAPPER_ACTION_MODE_PRESS;
    cfg->bindings[0][MAPPER_SRC_B][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_MODIFIER_KEY, MAPPER_MOD_LEFTALT, 0);
    cfg->bindings[0][MAPPER_SRC_B][MAPPER_GESTURE_HOLD].trigger_mode = MAPPER_ACTION_MODE_RELEASE;
    activate(8); tick(0, 1000); assert(modifier == MAPPER_MOD_LEFTALT);
    activate(4); assert(modifier == 0);
    tick(0, 1000); activate(12); assert(modifier == 0); /* same tick: Release wins */
}

static void test_keyboard_click_ack_and_combo_release_stop(void) {
    mapper_config_payload_t *cfg = prepare();
    cfg->combos[0] = (mapper_combo_t){.profile_mask = 1, .source_mask = 3,
        .action = {.type = MAPPER_ACTION_KEY, .param1 = 4, .trigger_mode = MAPPER_ACTION_MODE_CLICK,
                   .value = MAPPER_ACTION_INPUT_TAG | (10 << 2)}};
    input.buttons = 12;
    modifier = mapper_action_build_keycodes(keys, ++now_us); assert(keys[0] == 4);
    uint8_t neutral[6] = {0};
    mapper_action_note_keyboard_state(now_us, 0, neutral); /* endpoint not ready */
    now_us += 100000;
    mapper_action_build_keycodes(keys, now_us); assert(keys[0] == 4);
    mapper_action_note_keyboard_state(now_us, 0, keys);
    tick(12, 10000); assert(keys[0] == 0); /* one click, even if chord stays held */
    tick(0, 1000); tick(12, 1000); assert(keys[0] == 4);
    tick(0, 1000); tick(12, 1000); /* a second click queues during the first */
    tick(0, 8000); assert(keys[0] == 0);
    tick(0, 1000); assert(keys[0] == 4);
    tick(0, 10000); assert(keys[0] == 0);

    cfg = prepare();
    install_macro(cfg, MAPPER_SRC_A, MAPPER_MACRO_TRIGGER_RELEASE);
    cfg->combos[0] = (mapper_combo_t){.profile_mask = 1, .source_mask = 1u << MAPPER_SRC_B,
        .action = {.type = MAPPER_ACTION_STOP_ALL}};
    activate(12); tick(4, 1000); tick(0, 1000); tick(0, 1000);
    assert(keys[0] == 0); /* Stop suppresses a held macro's future release edge */

    cfg = prepare();
    install_macro(cfg, MAPPER_SRC_A, MAPPER_MACRO_TRIGGER_TOGGLE);
    cfg->bindings[0][MAPPER_SRC_B][MAPPER_GESTURE_HOLD] = output(MAPPER_ACTION_WHEEL_UP_TURBO, 0, 0);
    cfg->settings.wheel_turbo_hz = 10;
    activate(12); tick(0, 1000);
    for (unsigned i = 0; i < 100; i++) tick(0, 10000);
    assert(wheels == 11); /* latched wheel continues throughout macro playback */
}

int main(int argc, char **argv) {
    test_outputs(); test_tap_hold_double_and_wheel(); test_combo_and_suppression();
    test_macros_and_stop(); test_reset_and_backpressure();
    test_held_alt_survives_macro(); test_events_clicks_and_explicit_release();
    test_keyboard_click_ack_and_combo_release_stop();
    if (argc == 3) {
        mapper_config_payload_t payload;
        FILE *file = fopen(argv[1], "rb"); assert(file);
        assert(fread(&payload, sizeof(payload), 1, file) == 1); fclose(file);
        assert(mapper_config_apply_payload((uint8_t *)&payload));
        file = fopen(argv[2], "wb"); assert(file);
        assert(fwrite(mapper_config_get(), sizeof(payload), 1, file) == 1); fclose(file);
    }
    puts("toggle runtime: PASS");
    return 0;
}
