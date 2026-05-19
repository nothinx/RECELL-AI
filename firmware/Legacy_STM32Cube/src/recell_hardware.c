#include "recell_hardware.h"

// Note: This file contains the wrapper logic for STM32 HAL.
// Once generated via STM32CubeMX, the actual huart, htim, hadc handles will be used here.

void HW_Init(void) {
    // Dipanggil setelah MX_GPIO_Init, MX_TIM_Init, dsb.
    // Matikan semua aktuator di awal
    HW_Conveyor_Stop();
    HW_Load_SetCurrent(0);
    // Disable stepper
    // HAL_GPIO_WritePin(STEPPER_PORT, STEPPER_PIN_EN, GPIO_PIN_SET); 
}

void HW_Conveyor_Move(int speed, int direction) {
    // HAL_GPIO_WritePin(CONVEYOR_PORT, CONVEYOR_PIN_DIR, direction ? GPIO_PIN_SET : GPIO_PIN_RESET);
    // __HAL_TIM_SET_COMPARE(&htimX, TIM_CHANNEL_Y, speed);
}

void HW_Conveyor_Stop(void) {
    // __HAL_TIM_SET_COMPARE(&htimX, TIM_CHANNEL_Y, 0);
}

void HW_Stepper_Step(int steps, int direction) {
    // Enable Stepper
    // HAL_GPIO_WritePin(STEPPER_PORT, STEPPER_PIN_EN, GPIO_PIN_RESET);
    // HAL_GPIO_WritePin(STEPPER_PORT, STEPPER_PIN_DIR, direction ? GPIO_PIN_SET : GPIO_PIN_RESET);
    
    for(int i=0; i<steps; i++) {
        // HAL_GPIO_WritePin(STEPPER_PORT, STEPPER_PIN_STEP, GPIO_PIN_SET);
        // HAL_Delay(1); // Kasih delay 1ms (atau pakai timer interrupt untuk presisi)
        // HAL_GPIO_WritePin(STEPPER_PORT, STEPPER_PIN_STEP, GPIO_PIN_RESET);
        // HAL_Delay(1);
    }
    
    // Disable Stepper
    // HAL_GPIO_WritePin(STEPPER_PORT, STEPPER_PIN_EN, GPIO_PIN_SET);
}

void HW_Stepper_Sort(char grade) {
    // Contoh logika posisi bin (Grade A ke kiri, B tengah, Recycle kanan)
    if(grade == 'A') {
        HW_Stepper_Step(200, 1); // 200 step CW
    } else if(grade == 'B') {
        // Tetap di tengah atau geser dikit
    } else if(grade == 'R') {
        HW_Stepper_Step(200, 0); // 200 step CCW
    }
    
    // Kembali ke posisi Home (Opsional)
    // HW_Stepper_Step(200, kembali);
}

void HW_Load_SetCurrent(int pwm_value) {
    // Mengatur bukaan MOSFET
    // __HAL_TIM_SET_COMPARE(&htim_load, TIM_CHANNEL_LOAD, pwm_value);
}

float HW_ADC_ReadVoltage(void) {
    // HAL_ADC_Start(&hadc1);
    // HAL_ADC_PollForConversion(&hadc1, 10);
    // uint32_t raw = HAL_ADC_GetValue(&hadc1);
    // return (raw * 3.3f / 4095.0f) * VOLTAGE_DIVIDER_RATIO;
    return 3.75f; // Mock value
}

float HW_ADC_ReadCurrent(void) {
    // Sama seperti baca tegangan, tapi hitung dari V_shunt
    return 1.0f; // Mock value
}
