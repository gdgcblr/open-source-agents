package com.example.order;

public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    public String submitOrder(String customerId, double amount) {
        return orderService.createOrder(customerId, amount);
    }
}

