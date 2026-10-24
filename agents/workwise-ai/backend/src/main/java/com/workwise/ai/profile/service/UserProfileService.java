package com.workwise.ai.profile.service;

import com.workwise.ai.common.auth.CurrentUser;
import com.workwise.ai.common.exception.AccessDeniedException;
import com.workwise.ai.common.exception.ResourceNotFoundException;
import com.workwise.ai.profile.domain.UserProfile;
import com.workwise.ai.profile.repository.UserProfileRepository;
import com.workwise.ai.profile.web.UserProfileMapper;
import com.workwise.ai.profile.web.UserProfileRequest;
import com.workwise.ai.profile.web.UserProfileResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@Transactional
public class UserProfileService {

    private final UserProfileRepository repository;
    private final UserProfileMapper mapper;

    public UserProfileService(UserProfileRepository repository, UserProfileMapper mapper) {
        this.repository = repository;
        this.mapper = mapper;
    }

    public UserProfileResponse create(UserProfileRequest request) {
        UserProfile entity = new UserProfile();
        mapper.applyToEntity(request, entity);
        entity.setOwnerUserId(CurrentUser.get());
        return mapper.toResponse(repository.save(entity));
    }

    @Transactional(readOnly = true)
    public UserProfileResponse get(UUID id) {
        return mapper.toResponse(findOwned(id));
    }

    @Transactional(readOnly = true)
    public List<UserProfileResponse> listMine() {
        return repository.findByOwnerUserId(CurrentUser.get()).stream().map(mapper::toResponse).toList();
    }

    public UserProfileResponse update(UUID id, UserProfileRequest request) {
        UserProfile entity = findOwned(id);
        mapper.applyToEntity(request, entity);
        return mapper.toResponse(repository.save(entity));
    }

    /** Resolves a profile and verifies it belongs to the current demo user. */
    @Transactional(readOnly = true)
    public UserProfile findOwned(UUID id) {
        UserProfile entity = repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Profile not found: " + id));
        String currentUserId = CurrentUser.get();
        if (!entity.getOwnerUserId().equals(currentUserId)) {
            throw new AccessDeniedException("You do not have access to this profile");
        }
        return entity;
    }
}
