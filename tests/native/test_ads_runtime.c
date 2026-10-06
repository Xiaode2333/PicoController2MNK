/* Run the real mapper engine against a fake input snapshot and USB endpoint. */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "mapper_action.h"
#include "mapper_store.h"

static mapper_input_state_t input;
static int total_x, total_y;
static uint64_t clock_us = 1000000u;

void mapper_input_snapshot(mapper_input_state_t *state) { *state = input; }
void mapper_parser_set_calibration(uint16_t x, uint16_t y, float deadzone) {
    (void)x; (void)y; (void)deadzone;
}
void mapper_store_init(void) { mapper_config_init_defaults(); }

bool tud_hid_n_mouse_report(uint8_t instance, uint8_t report_id, uint8_t buttons,
                            int8_t x, int8_t y, int8_t wheel, int8_t pan) {
    (void)instance; (void)report_id; (void)buttons; (void)wheel; (void)pan;
    total_x += x;
    total_y += y;
    return true;
}

static int tick(void) {
    int before = total_x;
    clock_us += 1000u;
    assert(mapper_action_send_mouse(clock_us));
    return total_x - before;
}

static void prepare(mapper_source_t aim_source, uint32_t buttons) {
    mapper_action_init();
    mapper_config_payload_t *cfg = mapper_config_get();
    cfg->settings.active_profile = 1;
    cfg->settings.profile2_accel_enabled = 0;
    cfg->settings.mouse_speed_x[1] = 4000;
    cfg->settings.mouse_speed_y[1] = 6000;
    cfg->profile2_stick.rb_speed_x = 1000;
    cfg->profile2_stick.rb_speed_y = 2000;
    mapper_config_set_mouse_modes(cfg, 100, 0.0f, 50, 0.0f);
    mapper_config_set_profile2_aim_source(cfg, aim_source);
    memset(&input, 0, sizeof(input));
    input.buttons = buttons;
    input.rx = input.ry = 0.5f;
    tick();
    total_x = total_y = 0;
}

static void expect_motion(mapper_source_t aim_source, uint32_t buttons, bool ads) {
    prepare(aim_source, buttons);
    for (int i = 0; i < 64; ++i) tick();
    assert(total_x >= (ads ? 32 : 128) - 1 && total_x <= (ads ? 32 : 128) + 1);
    assert(total_y >= (ads ? 64 : 192) - 1 && total_y <= (ads ? 64 : 192) + 1);
}

static void test_config_validation(void) {
    mapper_config_init_defaults();
    mapper_config_payload_t *cfg = mapper_config_get();
    assert(mapper_config_profile2_aim_source(NULL) == MAPPER_SRC_RB);
    assert(mapper_config_profile2_aim_source(cfg) == MAPPER_SRC_RB);
    for (unsigned source = 0; source < MAPPER_SOURCE_COUNT; ++source) {
        mapper_config_set_profile2_aim_source(cfg, (mapper_source_t)source);
        assert(mapper_config_profile2_aim_source(cfg) == (mapper_source_t)source);
        assert(mapper_config_validate());
    }
    mapper_config_set_profile2_aim_source(cfg, MAPPER_SRC_LT);
    mapper_config_set_profile2_aim_source(cfg, (mapper_source_t)MAPPER_SOURCE_COUNT);
    assert(mapper_config_profile2_aim_source(cfg) == MAPPER_SRC_LT);
    cfg->macros[6].reserved[0] = cfg->macros[6].reserved[1] = 0;
    assert(mapper_config_profile2_aim_source(cfg) == MAPPER_SRC_RB);
    assert(mapper_config_validate());
    cfg->macros[6].reserved[0] = MAPPER_SOURCE_COUNT;
    cfg->macros[6].reserved[1] = MAPPER_PROFILE2_AIM_SOURCE_TAG >> 8;
    assert(!mapper_config_validate());
}

static void test_motion_and_release(void) {
    expect_motion(MAPPER_SRC_LT, 0x800000u, true);
    expect_motion(MAPPER_SRC_LT, 0x000040u, false); /* RB no longer means ADS. */
    expect_motion(MAPPER_SRC_LT, 0x800040u, true);
    expect_motion(MAPPER_SRC_LT, 0u, false);
    expect_motion(MAPPER_SRC_RB, 0x000040u, true); /* Existing configs. */
    expect_motion(MAPPER_SRC_RB, 0x800000u, false);
    expect_motion(MAPPER_SRC_A, 0x000008u, true); /* Logical IDs != report bits. */

    prepare(MAPPER_SRC_LT, 0x800000u);
    for (int i = 0; i < 64; ++i) tick();
    assert(total_x >= 31 && total_x <= 33);
    input.buttons = 0;
    total_x = total_y = 0;
    for (int i = 0; i < 64; ++i) tick();
    assert(total_x >= 127 && total_x <= 129);

    prepare(MAPPER_SRC_LT, 0x800000u);
    mapper_config_get()->settings.active_profile = 0;
    mapper_config_get()->settings.mouse_speed_x[0] = 4000;
    total_x = total_y = 0;
    for (int i = 0; i < 64; ++i) tick();
    assert(total_x >= 127 && total_x <= 129); /* ADS remains Profile 2 only. */
}

static void test_ads_acceleration_switch_resets_delay(void) {
    prepare(MAPPER_SRC_LT, 0x800000u);
    mapper_config_payload_t *cfg = mapper_config_get();
    cfg->settings.profile2_accel_enabled = 1;
    cfg->profile2_stick.rb_delay_ms = 3;
    cfg->profile2_stick.rb_ramp_ms = 0;
    cfg->profile2_stick.rb_extra_x = 2000;
    cfg->profile2_stick.no_rb_ramp_ms = 0;
    cfg->profile2_stick.no_rb_extra_x = 4000;
    input.rx = 1.0f;
    input.ry = 0.0f;
    assert(tick() == 1);
    assert(tick() == 1);
    for (int i = 0; i < 5; ++i) tick();
    assert(tick() == 3);
    input.buttons = 0x000040u; /* RB uses hip-fire acceleration when Aim is LT. */
    assert(tick() == 8);
    input.buttons = 0x800000u;
    assert(tick() == 1); /* A new ADS press starts its delay again. */
}

int main(int argc, char **argv) {
    test_config_validation();
    test_motion_and_release();
    test_ads_acceleration_switch_resets_delay();
    if (argc == 3) {
        mapper_config_payload_t payload;
        FILE *file = fopen(argv[1], "rb");
        assert(file != NULL);
        assert(fread(&payload, sizeof(payload), 1, file) == 1);
        fclose(file);
        assert(mapper_config_apply_payload((const uint8_t *)&payload));
        mapper_config_payload_t *cfg = mapper_config_get();
        assert(mapper_config_profile2_aim_source(cfg) == MAPPER_SRC_LT);
        assert(cfg->profile2_stick.rb_speed_x == 1234);
        assert(cfg->profile2_stick.rb_speed_y == 2345);
        mapper_config_set_profile2_aim_source(cfg, MAPPER_SRC_A);
        file = fopen(argv[2], "wb");
        assert(file != NULL);
        assert(fwrite(cfg, sizeof(*cfg), 1, file) == 1);
        fclose(file);
    }
    puts("ADS engine passed: selected button, release, legacy RB, acceleration transitions, payload compatibility.");
    return 0;
}
