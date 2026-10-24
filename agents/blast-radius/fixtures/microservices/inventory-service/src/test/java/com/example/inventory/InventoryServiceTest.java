package com.example.inventory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class InventoryServiceTest {

    @Test
    public void testCheckStock() {
        InventoryService service = new InventoryService();
        assertTrue(service.checkStock("SKU-99", 5));
    }
}

