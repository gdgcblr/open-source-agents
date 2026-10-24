package com.workwise.ai.feedback.repository;

import com.workwise.ai.feedback.domain.UserFeedback;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface UserFeedbackRepository extends JpaRepository<UserFeedback, UUID> {
}
