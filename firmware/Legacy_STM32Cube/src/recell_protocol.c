#include "recell_protocol.h"
#include "recell_hardware.h"
#include <stdio.h>
#include <string.h>

// Global State
SystemState_t current_state = STATE_IDLE;

/**
 * @brief Simple string-based JSON command parser.
 * Works well enough for predefined C strings without needing heavy libraries.
 */
void RECELL_ProcessCommand(char* json_str) {
    if(strstr(json_str, "\"cmd\": \"TEST_CONVEYOR\"")) {
        // Mock command: {"cmd": "TEST_CONVEYOR"}
        HW_Conveyor_Move(50, 1);
        RECELL_SendTelemetry(0, 0, "TESTING_CONVEYOR");
    } 
    else if(strstr(json_str, "\"cmd\": \"STOP_CONVEYOR\"")) {
        HW_Conveyor_Stop();
        RECELL_SendTelemetry(0, 0, "IDLE");
    }
    else if(strstr(json_str, "\"cmd\": \"TEST_STEPPER\"")) {
        // Putar kiri lalu kanan
        HW_Stepper_Step(100, 1);
        // HAL_Delay(500);
        HW_Stepper_Step(100, 0);
        RECELL_SendTelemetry(0, 0, "STEPPER_DONE");
    }
    else if(strstr(json_str, "\"cmd\": \"TEST_LOAD\"")) {
        // Nyalakan mosfet sebentar
        HW_Load_SetCurrent(100);
        float v = HW_ADC_ReadVoltage();
        float i = HW_ADC_ReadCurrent();
        HW_Load_SetCurrent(0); // Matikan lagi
        RECELL_SendTelemetry(v, i, "LOAD_TEST_DONE");
    }
    else if(strstr(json_str, "\"cmd\": \"START_SOH\"")) {
        current_state = STATE_SOH_MEASURING;
        RECELL_Measure_SoH();
    }
    else if(strstr(json_str, "\"cmd\": \"SORT\"")) {
        if(strstr(json_str, "\"grade\": \"A\"")) HW_Stepper_Sort('A');
        else if(strstr(json_str, "\"grade\": \"B\"")) HW_Stepper_Sort('B');
        else if(strstr(json_str, "\"grade\": \"R\"")) HW_Stepper_Sort('R');
        RECELL_SendTelemetry(0, 0, "SORT_DONE");
    }
}

/**
 * @brief Handles the Constant Current Load logic
 */
void RECELL_Measure_SoH(void) {
    if(current_state != STATE_SOH_MEASURING) return;

    // Nyalakan load
    HW_Load_SetCurrent(128); // Contoh nilai PWM
    
    // Baca sensor
    float v_start = HW_ADC_ReadVoltage();
    // Tunggu beberapa ms (HAL_Delay)
    float v_drop = HW_ADC_ReadVoltage();
    float i = HW_ADC_ReadCurrent();
    
    HW_Load_SetCurrent(0); // Matikan Load
    
    // Kirim data
    RECELL_SendTelemetry(v_drop, i, "MEASURING_DONE");

    current_state = STATE_IDLE;
}

/**
 * @brief Sends JSON telemetry back to Jetson
 */
void RECELL_SendTelemetry(float volt, float curr, char* status) {
    char buffer[128];
    sprintf(buffer, "{\"volt\":%.2f, \"curr\":%.2f, \"status\":\"%s\"}\n", volt, curr, status);
    // HAL_UART_Transmit(&huart2, (uint8_t*)buffer, strlen(buffer), 10);
}
