package com.example.order;

public class OrderService {

    private final PaymentClient paymentClient;

    public OrderService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }

    public String createOrder(String customerId, double totalAmount) {
        validateOrder(totalAmount);
        String txId = paymentClient.processPayment("ORD-1", totalAmount, "USD");
        return "ORDER-CONFIRMED:" + txId;
    }

    public void validateOrder(double totalAmount) {
        if (totalAmount < 1.0) {
            throw new IllegalArgumentException("Minimum order total is 1.0");
        }
    }

    public boolean cancelOrder(String orderId) {
        return paymentClient.refundPayment("REF-" + orderId);
    }
}

