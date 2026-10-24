package com.workwise.ai.common.config;

import com.workwise.ai.relevance.config.RelevanceProperties;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationPropertiesScan(basePackageClasses = RelevanceProperties.class)
public class PropertiesConfig {
}
