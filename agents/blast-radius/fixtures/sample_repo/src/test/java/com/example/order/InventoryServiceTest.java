package com.example.order;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class InventoryServiceTest {

    @Test
    public void testReserveStockSuccess() {
        InventoryService inventoryService = new InventoryService();
        assertTrue(inventoryService.reserveStock("SKU-123", 5));
    }
}

