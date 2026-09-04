#ifndef MAPPER_PROTOCOL_H
#define MAPPER_PROTOCOL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MAPPER_PROTOCOL_VERSION 1u
#define MAPPER_PROTOCOL_SCHEMA_VERSION 1u
#define MAPPER_PROTOCOL_MAX_PAYLOAD 8000u

void mapper_protocol_init(void);
void mapper_protocol_task(void);
const char *mapper_protocol_serial(void);

#ifdef __cplusplus
}
#endif

#endif /* MAPPER_PROTOCOL_H */
