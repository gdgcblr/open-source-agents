package com.example.service.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.time.Instant;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/users")
public class UserController {

    // SPEC: Requires OAuth2 scope 'user:read'
    // CODE: No authorization guard -> Public access vulnerability
    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> getUserById(@PathVariable("id") String id) {
        return ResponseEntity.ok(Map.of(
            "accountNumber", id,
            "email", "user@example.com",
            "accountStatus", "ACTIVE",
            "lastLoginTimestamp", Instant.now().toEpochMilli()
        ));
    }

    // SPEC: Requires OAuth2 scope 'admin:write'
    // CODE: Completely unguarded DELETE endpoint -> Critical security violation
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deleteUser(@PathVariable("id") String id) {
        return ResponseEntity.noContent().build();
    }
}