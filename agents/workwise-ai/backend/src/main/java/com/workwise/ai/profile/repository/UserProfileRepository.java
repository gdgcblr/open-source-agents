package com.workwise.ai.profile.repository;

import com.workwise.ai.profile.domain.UserProfile;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface UserProfileRepository extends JpaRepository<UserProfile, UUID> {
    List<UserProfile> findByOwnerUserId(String ownerUserId);
}
