#ifndef RECELL_PROT_H
#define RECELL_PROT_H

#include <stdint.h>

/**
 * @brief RECELL-AI System States
 */
typedef enum {
    STATE_IDLE,
    STATE_SOH_MEASURING,
    STATE_SORTING,
    STATE_ERROR
} SystemState_t;

/**
 * @brief Battery Grades
 */
typedef enum {
    GRADE_A,
    GRADE_B,
    GRADE_RECYCLE,
    GRADE_UNKNOWN
} BatteryGrade_t;

// Function prototypes for implementation later
void RECELL_Init(void);
void RECELL_ProcessCommand(char* json_str);
void RECELL_Measure_SoH(void);
void RECELL_ExecuteSort(BatteryGrade_t grade);
void RECELL_SendTelemetry(float volt, float curr, char* status);

#endif // RECELL_PROT_H
