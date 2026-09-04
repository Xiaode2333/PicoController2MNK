#include "mapper_store.h"

#include <stddef.h>
#include <string.h>

#include "hardware/flash.h"
#include "hardware/sync.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"

#include "mapper_config.h"

#define MAPPER_XIP_BASE 0x10000000u

typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint16_t version;
    uint16_t schema_version;
    uint32_t payload_size;
    uint32_t crc32;
    uint32_t save_counter;
    uint32_t header_crc32;
    uint8_t payload[MAPPER_STORE_PAYLOAD_SIZE];
    uint8_t pad[MAPPER_STORE_SLOT_SIZE - 24u - MAPPER_STORE_PAYLOAD_SIZE];
} mapper_store_record_t;

_Static_assert(sizeof(mapper_store_record_t) == MAPPER_STORE_SLOT_SIZE,
               "mapper_store_record_t must be one flash slot");
_Static_assert(offsetof(mapper_store_record_t, payload) == 24u,
               "mapper store header must remain 24 bytes");
_Static_assert((MAPPER_STORE_SLOT_SIZE % FLASH_SECTOR_SIZE) == 0u,
               "mapper store slot must be flash-sector aligned");
_Static_assert((MAPPER_STORE_SLOT_SIZE % FLASH_PAGE_SIZE) == 0u,
               "mapper store slot must be flash-page aligned");
_Static_assert(PICO_FLASH_SIZE_BYTES >= (2u * MAPPER_STORE_SLOT_SIZE),
               "flash must fit both mapper store slots");

static mapper_store_record_t g_store_record;
static bool g_store_has_valid_record = false;
static uint32_t g_store_active_slot = 0;
static uint32_t g_store_next_counter = 1;

static uint32_t store_slot_offset_a(void) {
    return (uint32_t)PICO_FLASH_SIZE_BYTES - (2u * MAPPER_STORE_SLOT_SIZE);
}

static uint32_t store_slot_offset_b(void) {
    return (uint32_t)PICO_FLASH_SIZE_BYTES - MAPPER_STORE_SLOT_SIZE;
}

static uint32_t store_slot_offset(uint32_t slot_index) {
    return slot_index == 0 ? store_slot_offset_a() : store_slot_offset_b();
}

static const uint8_t *store_slot_bytes(uint32_t offset) {
    return (const uint8_t *)(uintptr_t)(MAPPER_XIP_BASE + offset);
}

static bool store_record_valid(const mapper_store_record_t *record) {
    bool supported_schema =
        record->schema_version == MAPPER_STORE_SCHEMA_VERSION ||
        record->schema_version == MAPPER_STORE_SCHEMA_VERSION_LEGACY;
    if (record->magic != MAPPER_STORE_MAGIC ||
        record->version != MAPPER_STORE_VERSION ||
        !supported_schema ||
        record->payload_size != MAPPER_STORE_PAYLOAD_SIZE) {
        return false;
    }
    uint32_t header_crc = mapper_config_crc32(
        (const uint8_t *)record, offsetof(mapper_store_record_t, header_crc32));
    if (header_crc != record->header_crc32) {
        return false;
    }
    uint32_t crc = mapper_config_crc32(record->payload, MAPPER_STORE_PAYLOAD_SIZE);
    return crc == record->crc32;
}

static bool store_counter_is_newer(uint32_t candidate, uint32_t reference) {
    return (int32_t)(candidate - reference) > 0;
}

bool mapper_store_load(void) {
    uint32_t valid_count = 0;
    uint32_t best_counter = 0;
    uint32_t best_slot = 0;
    const mapper_store_record_t *best_record = NULL;

    for (uint32_t slot = 0; slot < 2; slot++) {
        const mapper_store_record_t *record =
            (const mapper_store_record_t *)store_slot_bytes(store_slot_offset(slot));
        if (!store_record_valid(record) ||
            !mapper_config_payload_valid(record->payload)) {
            continue;
        }
        valid_count++;
        if (valid_count == 1 ||
            store_counter_is_newer(record->save_counter, best_counter)) {
            best_counter = record->save_counter;
            best_slot = slot;
            best_record = record;
        }
    }

    if (valid_count == 0 || best_record == NULL) {
        g_store_has_valid_record = false;
        g_store_next_counter = 1;
        return false;
    }

    if (!mapper_config_apply_payload(best_record->payload)) {
        g_store_has_valid_record = false;
        return false;
    }

    /* Schema 1 shipped 12 ms as its default. Migrate only that exact legacy
     * default; explicit 0 and every other saved value remain untouched. A
     * later user save writes schema 2, where an explicit 12 stays 12. */
    if (best_record->schema_version == MAPPER_STORE_SCHEMA_VERSION_LEGACY &&
        mapper_config_get()->settings.mouse_release_grace_ms == 12u) {
        mapper_config_get()->settings.mouse_release_grace_ms = 40u;
    }

    g_store_has_valid_record = true;
    g_store_active_slot = best_slot;
    g_store_next_counter = best_counter + 1;
    return true;
}

typedef struct {
    uint32_t offset;
    const uint8_t *record_bytes;
} store_write_ctx_t;

static void __no_inline_not_in_flash_func(store_write_flash)(void *param) {
    store_write_ctx_t *ctx = (store_write_ctx_t *)param;
    flash_range_erase(ctx->offset, MAPPER_STORE_SLOT_SIZE);
    flash_range_program(ctx->offset, ctx->record_bytes, MAPPER_STORE_SLOT_SIZE);
}

bool mapper_store_save(void) {
    const mapper_config_payload_t *config = mapper_config_get();
    mapper_store_record_t *record = &g_store_record;

    if (!mapper_config_validate()) {
        return false;
    }

    memset(record, 0, sizeof(*record));
    record->magic = MAPPER_STORE_MAGIC;
    record->version = MAPPER_STORE_VERSION;
    record->schema_version = MAPPER_STORE_SCHEMA_VERSION;
    record->payload_size = MAPPER_STORE_PAYLOAD_SIZE;
    record->save_counter = g_store_next_counter;
    memcpy(record->payload, config, sizeof(*config));

    uint32_t crc = mapper_config_crc32(record->payload, MAPPER_STORE_PAYLOAD_SIZE);
    record->crc32 = crc;
    record->header_crc32 = mapper_config_crc32(
        (const uint8_t *)record, offsetof(mapper_store_record_t, header_crc32));

    uint32_t inactive_slot = g_store_active_slot == 0 ? 1u : 0u;
    uint32_t inactive_offset = store_slot_offset(inactive_slot);

    store_write_ctx_t ctx;
    ctx.offset = inactive_offset;
    ctx.record_bytes = (const uint8_t *)record;

    /* Both cores must be paused before flash erase/program. Core 1 is already
     * initialized as a lockout victim in core1_main() for mapper firmware. */
    uint32_t ints = save_and_disable_interrupts();
    bool locked = multicore_lockout_start_timeout_us(500000u);
    if (!locked) {
        restore_interrupts(ints);
        return false;
    }

    store_write_flash(&ctx);

    multicore_lockout_end_blocking();
    restore_interrupts(ints);

    const mapper_store_record_t *written =
        (const mapper_store_record_t *)store_slot_bytes(inactive_offset);
    if (!store_record_valid(written)) {
        return false;
    }

    g_store_active_slot = inactive_slot;
    g_store_next_counter++;
    g_store_has_valid_record = true;
    return true;
}

void mapper_store_init(void) {
    mapper_config_ensure_defaults();
    if (!mapper_store_load()) {
        mapper_config_factory_reset();
    }
}

bool mapper_store_is_persisted(void) {
    return g_store_has_valid_record;
}
