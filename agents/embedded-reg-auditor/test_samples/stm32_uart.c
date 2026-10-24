#include <stdint.h>

#define USART2_BASE 0x40004400U
#define UART_BAUD_RATE 115200U

typedef struct {
    volatile uint32_t CR1;
    volatile uint32_t CR2;
    volatile uint32_t CR3;
    volatile uint32_t BRR;
} USART_TypeDef;

void uart2_init(void) {
    USART_TypeDef *uart = (USART_TypeDef *)USART2_BASE;
    uart->BRR = UART_BAUD_RATE;
    uart->CR1 |= (1 << 31);
}