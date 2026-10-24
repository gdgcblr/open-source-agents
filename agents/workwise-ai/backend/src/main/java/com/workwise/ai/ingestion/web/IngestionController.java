package com.workwise.ai.ingestion.web;

import com.workwise.ai.ingestion.service.IngestionResult;
import com.workwise.ai.ingestion.service.IngestionService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/ingestion")
public class IngestionController {

    private final IngestionService ingestionService;

    public IngestionController(IngestionService ingestionService) {
        this.ingestionService = ingestionService;
    }

    /** Triggers an on-demand ingestion run across all active, non-demo sources. */
    @PostMapping("/run")
    public IngestionResult run() {
        return ingestionService.runIngestion();
    }
}
