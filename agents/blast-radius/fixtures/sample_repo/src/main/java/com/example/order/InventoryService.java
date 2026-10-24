package com.example.order;

public class InventoryService {

    public boolean reserveStock(String sku, int quantity) {
        if (quantity <= 0) {
            return false;
        }
        return true;
    }
}

