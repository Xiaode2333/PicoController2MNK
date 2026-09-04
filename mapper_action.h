#ifndef MAPPER_ACTION_H
#define MAPPER_ACTION_H

#include <stdbool.h>
#include <stdint.h>

#include "mapper_config.h"

#ifdef __cplusplus
extern "C" {
#endif

void mapper_action_init(void);
void mapper_action_reset(void);
void mapper_action_request_release(void);
void mapper_action_cycle_profile(void);
void mapper_action_toggle_output(void);
bool mapper_action_output_enabled(void);
bool mapper_action_release_pending(void);

/* These functions are called by main.c every output tick. */
uint8_t mapper_action_build_keycodes(uint8_t keycode[6], uint64_t now_us);
bool mapper_action_send_mouse(uint64_t now_us);
uint8_t mapper_action_last_mouse_buttons(void);
bool mapper_action_send_stale_mouse_hold(uint64_t now_us);
bool mapper_action_send_neutral_step(uint64_t now_us, bool keyboard_neutral);
void mapper_action_note_keyboard_state(uint64_t now_us, uint8_t modifier,
                                       const uint8_t keycode[6]);

void mapper_action_set_calibration(uint16_t rx_center, uint16_t ry_center,
                                   float right_deadzone);
void mapper_action_set_calibration_active(bool active);
void mapper_parser_set_calibration(uint16_t rx_center, uint16_t ry_center,
                                   float right_deadzone);
void mapper_input_snapshot(mapper_input_state_t *state);

#ifdef __cplusplus
}
#endif

#endif /* MAPPER_ACTION_H */
