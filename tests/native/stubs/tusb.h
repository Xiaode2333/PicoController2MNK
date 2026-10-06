#ifndef TEST_TUSB_H
#define TEST_TUSB_H
#include <stdbool.h>
#include <stdint.h>
#define HID_KEY_1 0x1E
#define HID_KEY_2 0x1F
#define HID_KEY_3 0x20
#define HID_KEY_4 0x21
#define HID_KEY_5 0x22
#define HID_KEY_A 0x04
#define HID_KEY_B 0x05
#define HID_KEY_C 0x06
#define HID_KEY_D 0x07
#define HID_KEY_E 0x08
#define HID_KEY_ESCAPE 0x29
#define HID_KEY_F 0x09
#define HID_KEY_G 0x0A
#define HID_KEY_GRAVE 0x35
#define HID_KEY_H 0x0B
#define HID_KEY_L 0x0F
#define HID_KEY_M 0x10
#define HID_KEY_Q 0x14
#define HID_KEY_R 0x15
#define HID_KEY_S 0x16
#define HID_KEY_SPACE 0x2C
#define HID_KEY_TAB 0x2B
#define HID_KEY_U 0x18
#define HID_KEY_V 0x19
#define HID_KEY_W 0x1A
#define HID_KEY_X 0x1B
#define HID_KEY_Z 0x1D
bool tud_hid_n_mouse_report(uint8_t instance, uint8_t report_id, uint8_t buttons,
                            int8_t x, int8_t y, int8_t wheel, int8_t pan);
#endif
