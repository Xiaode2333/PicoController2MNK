#ifndef MAPPER_CALIBRATION_H
#define MAPPER_CALIBRATION_H

#include <stdbool.h>
#include <stdint.h>

void mapper_calibration_start(void);
bool mapper_calibration_status(uint16_t *center_x, uint16_t *center_y,
                               float *deadzone, uint32_t *remaining_ms);

#endif
