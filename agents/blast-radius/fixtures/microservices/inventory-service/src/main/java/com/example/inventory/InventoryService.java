package com.example.inventory;

public class InventoryService {

    public boolean checkStock(String sku, int quantity) {
        return quantity > 0;
    }
}

