cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(PicoController2MNK C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

set(PICO_PIO_USB_PATH "${CMAKE_CURRENT_LIST_DIR}/Pico-PIO-USB" CACHE PATH "Pico-PIO-USB path")

# Reserve the final two 8 KiB sectors for mapper_store.c. The board header
# still exposes the physical 2 MiB size to the firmware, while the linker
# fails the build if code/data ever grows into the persistent config slots.
set(PICO_FLASH_SIZE_BYTES "(2 * 1024 * 1024) - (2 * 8192)")

pico_sdk_init()

function(add_pico_controller_target target_name)
    add_executable(${target_name}
        main.c
        mapper_config.c
        mapper_store.c
        mapper_action.c
        mapper_protocol.c

    )

    target_include_directories(${target_name} PRIVATE
        ${CMAKE_CURRENT_LIST_DIR}
    )

    target_link_libraries(${target_name}
        pico_stdlib
        pico_multicore
        hardware_flash
        pico_unique_id

        tinyusb_device
        tinyusb_host
        tinyusb_pico_pio_usb
    )

    pico_enable_stdio_usb(${target_name} 0)
    pico_enable_stdio_uart(${target_name} 0)

    pico_add_extra_outputs(${target_name})
endfunction()

add_pico_controller_target(pico_cdc_test)

add_pico_controller_target(pico_kbm_mapper)
target_compile_definitions(pico_kbm_mapper PRIVATE
    PICO_FIRMWARE_MAPPER=1
    KEYMOUSE_REPORT_RATE_HZ=8000
    FIRMWARE_PID=0x4007
    FIRMWARE_VERSION_MAJOR=2
    FIRMWARE_VERSION_MINOR=0
    FIRMWARE_VERSION_PATCH=6

    "FIRMWARE_PRODUCT_STRING=\"Pico KBM Mapper\""
)

add_pico_controller_target(pico_kbm_mapper_trace)
target_compile_definitions(pico_kbm_mapper_trace PRIVATE
    PICO_FIRMWARE_MAPPER=1
    MAPPER_ENABLE_CDC_STATUS=1
    DEBUG_PRINT_RAW_REPORTS=1
    MAPPER_TRACE_MOUSE_OUTPUT=1
    CAPTURE_SAMPLE_COUNT=250
    CAPTURE_START_DELAY_US=0
    CAPTURE_INTERVAL_US=4000
    KEYMOUSE_REPORT_RATE_HZ=8000
    FIRMWARE_PID=0x4008
    FIRMWARE_VERSION_MAJOR=2
    FIRMWARE_VERSION_MINOR=0
    FIRMWARE_VERSION_PATCH=6

    "FIRMWARE_PRODUCT_STRING=\"Pico KBM Mapper Trace\""
)
