#ifndef RECELL_HARDWARE_H
#define RECELL_HARDWARE_H

#include "stm32f4xx_hal.h" // Sesuaikan dengan HAL yang dipakai (misal f4xx)

/* ==========================================
 * PINOUT DEFINITIONS (Ubah bagian ini nanti)
 * ========================================== */

// 1. CONVEYOR MOTOR
#define CONVEYOR_PORT       GPIOA
#define CONVEYOR_PIN_DIR    GPIO_PIN_0
#define CONVEYOR_PIN_PWM    GPIO_PIN_1 // Timer Channel

// 2. SORTING STEPPER MOTOR
#define STEPPER_PORT        GPIOB
#define STEPPER_PIN_DIR     GPIO_PIN_10
#define STEPPER_PIN_STEP    GPIO_PIN_11
#define STEPPER_PIN_EN      GPIO_PIN_12

// 3. SENSORS (Proximity / IR)
#define SENSOR_PORT         GPIOC
#define SENSOR_PIN_ENTRY    GPIO_PIN_0
#define SENSOR_PIN_TEST     GPIO_PIN_1

// 4. CONSTANT CURRENT LOAD (MOSFET & ADC)
#define LOAD_PORT           GPIOA
#define LOAD_PIN_PWM        GPIO_PIN_5 // DAC / PWM untuk Gate MOSFET
#define SENSOR_PIN_VOLT     GPIO_PIN_6 // ADC In (Tegangan Baterai)
#define SENSOR_PIN_CURR     GPIO_PIN_7 // ADC In (Arus via Shunt Resistor)

/* ==========================================
 * HARDWARE CONTROL FUNCTIONS
 * ========================================== */
void HW_Init(void);
void HW_Conveyor_Move(int speed, int direction);
void HW_Conveyor_Stop(void);

void HW_Stepper_Sort(char grade);
void HW_Stepper_Step(int steps, int direction);

void HW_Load_SetCurrent(int pwm_value);
float HW_ADC_ReadVoltage(void);
float HW_ADC_ReadCurrent(void);

#endif // RECELL_HARDWARE_H
