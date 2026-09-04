#include "mapper_protocol.h"

#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "pico/unique_id.h"
#include "pico/stdlib.h"
#include "tusb.h"

#include "mapper_action.h"
#include "mapper_calibration.h"
#include "mapper_config.h"
#include "mapper_store.h"

#ifndef FIRMWARE_VERSION_MAJOR
#define FIRMWARE_VERSION_MAJOR 2u
#endif
#ifndef FIRMWARE_VERSION_MINOR
#define FIRMWARE_VERSION_MINOR 0u
#endif
#ifndef FIRMWARE_VERSION_PATCH
#define FIRMWARE_VERSION_PATCH 0u
#endif
#ifndef FIRMWARE_PID
#define FIRMWARE_PID 0x4007u
#endif
#ifndef FIRMWARE_PRODUCT_STRING
#define FIRMWARE_PRODUCT_STRING "Pico KBM Mapper"
#endif

#define PROTOCOL_MAGIC 0xA5u
#define PROTOCOL_HEADER_SIZE 6u
#define PROTOCOL_CRC_SIZE 4u
#define PROTOCOL_FRAME_MAX (PROTOCOL_HEADER_SIZE + MAPPER_PROTOCOL_MAX_PAYLOAD + PROTOCOL_CRC_SIZE)
#define PROTOCOL_RX_STALE_US 1000000u

typedef enum {
    CMD_PING = 0x01,
    CMD_GET_CONFIG = 0x02,
    CMD_SET_CONFIG = 0x03,
    CMD_SAVE_CONFIG = 0x04,
    CMD_FACTORY_RESET = 0x05,
    CMD_MONITOR = 0x06,
    CMD_START_CALIBRATION = 0x07,
    CMD_CALIBRATION_STATUS = 0x08,
    RESP_ACK_BASE = 0x80,
    RESP_STATE = 0x21,
    RESP_ERROR = 0x7F
} protocol_command_t;

typedef enum {
    ERR_NONE = 0,
    ERR_BAD_CRC = 1,
    ERR_BAD_LENGTH = 2,
    ERR_BAD_COMMAND = 3,
    ERR_INVALID_CONFIG = 4,
    ERR_FLASH_WRITE = 5
} protocol_error_t;

typedef struct __attribute__((packed)) {
    uint8_t magic[8];
    uint16_t protocol_version;
    uint16_t schema_version;
    uint16_t firmware_major;
    uint16_t firmware_minor;
    uint16_t firmware_patch;
    uint16_t vid;
    uint16_t pid;
    uint8_t product[32];
    uint8_t serial[32];
    uint8_t persisted;
    uint8_t reserved[3];
} protocol_identity_t;

typedef struct __attribute__((packed)) {
    uint8_t active;
    uint16_t center_x;
    uint16_t center_y;
    float deadzone;
    uint32_t remaining_ms;
} protocol_calibration_status_t;

typedef struct __attribute__((packed)) {
    uint32_t buttons;
    float lx;
    float ly;
    float rx;
    float ry;
    uint16_t raw_lx;
    uint16_t raw_ly;
    uint16_t raw_rx;
    uint16_t raw_ry;
} protocol_state_t;

_Static_assert(sizeof(protocol_state_t) == 28, "protocol_state_t must be 28 bytes");
_Static_assert(sizeof(protocol_calibration_status_t) == 13,
               "protocol_calibration_status_t must be 13 bytes");

static uint8_t g_rx_buf[PROTOCOL_FRAME_MAX];
static uint16_t g_rx_len = 0;
static uint8_t g_tx_buf[PROTOCOL_FRAME_MAX];
static uint16_t g_tx_len = 0;
static uint16_t g_tx_offset = 0;
/* Age the frame candidate at the front of the stream, rather than the most
 * recently received byte. Otherwise periodic traffic can keep a corrupted
 * legal-looking length alive forever and strand valid frames behind it. */
static uint64_t g_rx_candidate_since_us = 0;
static bool g_cdc_was_connected = false;

static char g_serial[2 * PICO_UNIQUE_BOARD_ID_SIZE_BYTES + 1];
static protocol_identity_t g_identity;
static uint32_t g_monitor_interval_ms = 0;
static uint64_t g_next_state_us = 0;

static uint32_t protocol_crc32(const uint8_t *data, uint32_t len) {
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

static bool protocol_tx_pending(void) {
    return g_tx_offset < g_tx_len;
}

static void protocol_reset_tx(void) {
    g_tx_len = 0;
    g_tx_offset = 0;
}

static void protocol_drain_tx(void) {
    if (!protocol_tx_pending() || !tud_cdc_connected()) return;

    while (protocol_tx_pending()) {
        uint32_t available = tud_cdc_write_available();
        if (available == 0) break;

        uint32_t remaining = (uint32_t)(g_tx_len - g_tx_offset);
        uint32_t chunk = remaining < available ? remaining : available;
        uint32_t written = tud_cdc_write(&g_tx_buf[g_tx_offset], chunk);
        if (written == 0) break;
        g_tx_offset = (uint16_t)(g_tx_offset + written);
    }

    tud_cdc_write_flush();
    if (!protocol_tx_pending()) {
        protocol_reset_tx();
    }
}

static bool protocol_send_frame(uint8_t type, const uint8_t *payload, uint16_t len) {
    if (len > MAPPER_PROTOCOL_MAX_PAYLOAD || protocol_tx_pending()) return false;

    g_tx_buf[0] = PROTOCOL_MAGIC;
    g_tx_buf[1] = MAPPER_PROTOCOL_VERSION;
    g_tx_buf[2] = type;
    g_tx_buf[3] = 0;
    g_tx_buf[4] = (uint8_t)(len & 0xFFu);
    g_tx_buf[5] = (uint8_t)((len >> 8) & 0xFFu);
    if (len != 0) {
        memcpy(&g_tx_buf[PROTOCOL_HEADER_SIZE], payload, len);
    }

    uint32_t crc = protocol_crc32(g_tx_buf, PROTOCOL_HEADER_SIZE + len);
    uint32_t crc_pos = PROTOCOL_HEADER_SIZE + len;
    g_tx_buf[crc_pos + 0] = (uint8_t)(crc & 0xFFu);
    g_tx_buf[crc_pos + 1] = (uint8_t)((crc >> 8) & 0xFFu);
    g_tx_buf[crc_pos + 2] = (uint8_t)((crc >> 16) & 0xFFu);
    g_tx_buf[crc_pos + 3] = (uint8_t)((crc >> 24) & 0xFFu);

    g_tx_len = (uint16_t)(PROTOCOL_HEADER_SIZE + len + PROTOCOL_CRC_SIZE);
    g_tx_offset = 0;
    protocol_drain_tx();
    return true;
}

static void protocol_send_error(uint8_t command, protocol_error_t code,
                                const char *message) {
    uint8_t payload[36];
    memset(payload, 0, sizeof(payload));
    payload[0] = (uint8_t)(code & 0xFFu);
    payload[1] = (uint8_t)((code >> 8) & 0xFFu);
    payload[2] = (uint8_t)((code >> 16) & 0xFFu);
    payload[3] = (uint8_t)((code >> 24) & 0xFFu);
    if (message != NULL) {
        size_t max_len = sizeof(payload) - 4u;
        size_t msg_len = strlen(message);
        if (msg_len > max_len) msg_len = max_len;
        memcpy(&payload[4], message, msg_len);
    }
    protocol_send_frame(RESP_ERROR, payload, sizeof(payload));
    (void)command;
}

static void protocol_send_ack(uint8_t command, const uint8_t *payload, uint16_t len) {
    protocol_send_frame((uint8_t)(RESP_ACK_BASE | command), payload, len);
}

static void protocol_send_status(uint8_t command, uint32_t status) {
    uint8_t payload[4];
    payload[0] = (uint8_t)(status & 0xFFu);
    payload[1] = (uint8_t)((status >> 8) & 0xFFu);
    payload[2] = (uint8_t)((status >> 16) & 0xFFu);
    payload[3] = (uint8_t)((status >> 24) & 0xFFu);
    protocol_send_ack(command, payload, sizeof(payload));
}

void mapper_protocol_init(void) {
    pico_get_unique_board_id_string(g_serial, sizeof(g_serial));

    memset(&g_identity, 0, sizeof(g_identity));
    memcpy(g_identity.magic, "P2MNCFG", 8);
    g_identity.protocol_version = MAPPER_PROTOCOL_VERSION;
    g_identity.schema_version = MAPPER_PROTOCOL_SCHEMA_VERSION;
    g_identity.firmware_major = FIRMWARE_VERSION_MAJOR;
    g_identity.firmware_minor = FIRMWARE_VERSION_MINOR;
    g_identity.firmware_patch = FIRMWARE_VERSION_PATCH;
    g_identity.vid = 0xCafe;
    g_identity.pid = FIRMWARE_PID;
    strncpy((char *)g_identity.product, FIRMWARE_PRODUCT_STRING,
            sizeof(g_identity.product) - 1u);
    strncpy((char *)g_identity.serial, g_serial, sizeof(g_identity.serial) - 1u);
    g_identity.persisted = mapper_store_is_persisted() ? 1u : 0u;
}

const char *mapper_protocol_serial(void) {
    return g_serial;
}

static void protocol_handle_frame(uint8_t type, const uint8_t *payload, uint16_t len) {
    uint8_t status_payload[4];

    switch (type) {
        case CMD_PING:
            g_identity.persisted = mapper_store_is_persisted() ? 1u : 0u;
            protocol_send_ack(CMD_PING, (const uint8_t *)&g_identity,
                              sizeof(g_identity));
            break;

        case CMD_GET_CONFIG:
            if (len != 0) {
                protocol_send_error(type, ERR_BAD_LENGTH, "GET_CONFIG takes no payload");
                return;
            }
            protocol_send_ack(CMD_GET_CONFIG,
                              (const uint8_t *)mapper_config_get(),
                              MAPPER_CONFIG_PAYLOAD_SIZE);
            break;

        case CMD_SET_CONFIG:
            if (len != MAPPER_CONFIG_PAYLOAD_SIZE) {
                protocol_send_error(type, ERR_BAD_LENGTH, "bad config payload size");
                return;
            }
            if (!mapper_config_apply_payload(payload)) {
                protocol_send_error(type, ERR_INVALID_CONFIG, "config validation failed");
                return;
            }
            mapper_action_reset();
            mapper_parser_set_calibration(mapper_config_get()->settings.right_center_x,
                                          mapper_config_get()->settings.right_center_y,
                                          mapper_config_get()->settings.right_deadzone);
            protocol_send_status(type, 1);
            break;

        case CMD_SAVE_CONFIG:
            if (len != 0) {
                protocol_send_error(type, ERR_BAD_LENGTH, "SAVE_CONFIG takes no payload");
                return;
            }
            if (!mapper_store_save()) {
                protocol_send_error(type, ERR_FLASH_WRITE, "flash write failed");
                return;
            }
            status_payload[0] = 1;
            status_payload[1] = 0;
            status_payload[2] = 0;
            status_payload[3] = 0;
            protocol_send_ack(CMD_SAVE_CONFIG, status_payload, sizeof(status_payload));
            break;

        case CMD_FACTORY_RESET:
            if (len != 0) {
                protocol_send_error(type, ERR_BAD_LENGTH, "FACTORY_RESET takes no payload");
                return;
            }
            mapper_config_factory_reset();
            mapper_action_reset();
            mapper_parser_set_calibration(mapper_config_get()->settings.right_center_x,
                                          mapper_config_get()->settings.right_center_y,
                                          mapper_config_get()->settings.right_deadzone);
            if (!mapper_store_save()) {
                protocol_send_error(type, ERR_FLASH_WRITE, "flash write failed");
                return;
            }
            protocol_send_status(type, 1);
            break;

        case CMD_MONITOR:
            if (len < 4) {
                protocol_send_error(type, ERR_BAD_LENGTH, "MONITOR needs 4 byte interval");
                return;
            }
            g_monitor_interval_ms = (uint32_t)payload[0] |
                                    ((uint32_t)payload[1] << 8) |
                                    ((uint32_t)payload[2] << 16) |
                                    ((uint32_t)payload[3] << 24);
            if (g_monitor_interval_ms != 0 && g_monitor_interval_ms < 10) {
                g_monitor_interval_ms = 10;
            }
            g_next_state_us = 0;
            protocol_send_status(type, g_monitor_interval_ms);
            break;

        case CMD_START_CALIBRATION:
        case CMD_CALIBRATION_STATUS: {
            if (len != 0) {
                protocol_send_error(type, ERR_BAD_LENGTH,
                                    "calibration command takes no payload");
                return;
            }
            if (type == CMD_START_CALIBRATION) {
                mapper_calibration_start();
            }
            protocol_calibration_status_t calibration = {0};
            uint16_t center_x = 0;
            uint16_t center_y = 0;
            float deadzone = 0.0f;
            uint32_t remaining_ms = 0;
            calibration.active = mapper_calibration_status(
                &center_x, &center_y, &deadzone, &remaining_ms
            ) ? 1u : 0u;
            calibration.center_x = center_x;
            calibration.center_y = center_y;
            calibration.deadzone = deadzone;
            calibration.remaining_ms = remaining_ms;
            protocol_send_ack(type, (const uint8_t *)&calibration,
                              sizeof(calibration));
            break;
        }

        default:
            protocol_send_error(type, ERR_BAD_COMMAND, "unknown command");
            break;
    }
}

static void protocol_drop_rx_prefix(uint16_t count, uint64_t now_us) {
    if (count >= g_rx_len) {
        g_rx_len = 0;
        g_rx_candidate_since_us = 0;
        return;
    }

    memmove(g_rx_buf, g_rx_buf + count, g_rx_len - count);
    g_rx_len = (uint16_t)(g_rx_len - count);
    g_rx_candidate_since_us = now_us;
}

static void protocol_handle_rx(uint64_t now_us) {
    if (g_rx_len != 0 && g_rx_len < PROTOCOL_HEADER_SIZE &&
        g_rx_candidate_since_us != 0 &&
        now_us - g_rx_candidate_since_us >= PROTOCOL_RX_STALE_US) {
        g_rx_len = 0;
        g_rx_candidate_since_us = 0;
        return;
    }

    while (!protocol_tx_pending() && g_rx_len >= PROTOCOL_HEADER_SIZE) {
        if (g_rx_buf[0] != PROTOCOL_MAGIC) {
            protocol_drop_rx_prefix(1, now_us);
            continue;
        }

        if (g_rx_buf[1] != MAPPER_PROTOCOL_VERSION || g_rx_buf[3] != 0) {
            protocol_drop_rx_prefix(1, now_us);
            continue;
        }

        uint16_t payload_len = (uint16_t)g_rx_buf[4] |
                               ((uint16_t)g_rx_buf[5] << 8);
        if (payload_len > MAPPER_PROTOCOL_MAX_PAYLOAD) {
            protocol_drop_rx_prefix(1, now_us);
            continue;
        }

        uint32_t frame_len = PROTOCOL_HEADER_SIZE + payload_len + PROTOCOL_CRC_SIZE;
        if (g_rx_len < frame_len) {
            if (g_rx_candidate_since_us != 0 &&
                now_us - g_rx_candidate_since_us >= PROTOCOL_RX_STALE_US) {
                protocol_drop_rx_prefix(1, now_us);
                continue;
            }
            return;
        }

        uint32_t crc_expected = (uint32_t)g_rx_buf[PROTOCOL_HEADER_SIZE + payload_len + 0] |
                                ((uint32_t)g_rx_buf[PROTOCOL_HEADER_SIZE + payload_len + 1] << 8) |
                                ((uint32_t)g_rx_buf[PROTOCOL_HEADER_SIZE + payload_len + 2] << 16) |
                                ((uint32_t)g_rx_buf[PROTOCOL_HEADER_SIZE + payload_len + 3] << 24);
        uint32_t crc_actual = protocol_crc32(g_rx_buf,
                                             PROTOCOL_HEADER_SIZE + payload_len);

        if (crc_expected == crc_actual) {
            protocol_handle_frame(g_rx_buf[2], &g_rx_buf[PROTOCOL_HEADER_SIZE],
                                  payload_len);
        } else {
            protocol_send_error(g_rx_buf[2], ERR_BAD_CRC, "CRC mismatch");
            protocol_drop_rx_prefix(1, now_us);
            continue;
        }

        protocol_drop_rx_prefix((uint16_t)frame_len, now_us);
    }
}

void mapper_protocol_task(void) {
    bool connected = tud_cdc_connected();
    if (!connected) {
        if (g_cdc_was_connected) {
            tud_cdc_read_flush();
            tud_cdc_write_clear();
        }
        g_cdc_was_connected = false;
        protocol_reset_tx();
        g_rx_len = 0;
        g_rx_candidate_since_us = 0;
        g_monitor_interval_ms = 0;
        g_next_state_us = 0;
        return;
    }
    g_cdc_was_connected = true;

    uint64_t now_us = time_us_64();

    while (tud_cdc_available()) {
        uint8_t chunk[64];
        uint32_t count = tud_cdc_read(chunk, sizeof(chunk));
        for (uint32_t i = 0; i < count; i++) {
            if (g_rx_len < sizeof(g_rx_buf)) {
                if (g_rx_len == 0) {
                    g_rx_candidate_since_us = now_us;
                }
                g_rx_buf[g_rx_len++] = chunk[i];
            } else {
                memmove(g_rx_buf, g_rx_buf + 1, g_rx_len - 1);
                g_rx_buf[g_rx_len - 1] = chunk[i];
                g_rx_candidate_since_us = now_us;
            }
        }
    }

    protocol_drain_tx();
    if (!protocol_tx_pending()) {
        protocol_handle_rx(now_us);
        protocol_drain_tx();
    }

    if (g_monitor_interval_ms == 0 || protocol_tx_pending()) {
        return;
    }

    now_us = time_us_64();
    if (g_next_state_us == 0 || now_us >= g_next_state_us) {
        mapper_input_state_t input;
        mapper_input_snapshot(&input);

        protocol_state_t state;
        state.buttons = input.buttons;
        state.lx = input.lx;
        state.ly = input.ly;
        state.rx = input.rx;
        state.ry = input.ry;
        state.raw_lx = input.raw_lx;
        state.raw_ly = input.raw_ly;
        state.raw_rx = input.raw_rx;
        state.raw_ry = input.raw_ry;

        protocol_send_frame(RESP_STATE, (const uint8_t *)&state, sizeof(state));
        g_next_state_us = now_us + (uint64_t)g_monitor_interval_ms * 1000u;
    }
}
