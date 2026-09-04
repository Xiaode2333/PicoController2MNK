#ifndef MAPPER_STORE_H
#define MAPPER_STORE_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MAPPER_STORE_MAGIC 0x4E4D3250u /* "P2MN" little-endian */
#define MAPPER_STORE_VERSION 2u
#define MAPPER_STORE_SCHEMA_VERSION_LEGACY 1u
#define MAPPER_STORE_SCHEMA_VERSION 2u
#define MAPPER_STORE_PAYLOAD_SIZE 8000u
#define MAPPER_STORE_SLOT_SIZE 8192u

void mapper_store_init(void);
bool mapper_store_save(void);
bool mapper_store_load(void);
bool mapper_store_is_persisted(void);

#ifdef __cplusplus
}
#endif

#endif /* MAPPER_STORE_H */
