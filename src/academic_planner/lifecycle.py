class InvalidLifecycleTransition(ValueError):
    pass


_ALLOWED_TRANSITIONS = {
    "section": {
        ("PROPOSED", "OPERATIONAL"),
        ("PROPOSED", "UNSTAFFED"),
        ("PROPOSED", "BLOCKED"),
        ("PROPOSED", "REJECTED"),
    },
    "workload_assignment": {
        ("PROPOSED", "APPROVED"),
        ("PROPOSED", "REJECTED"),
    },
}


def validate_lifecycle_transition(entity_type, previous_state, new_state):
    transition = (previous_state, new_state)
    if transition not in _ALLOWED_TRANSITIONS.get(entity_type, set()):
        raise InvalidLifecycleTransition(
            f"Invalid {entity_type} lifecycle transition: "
            f"{previous_state} -> {new_state}"
        )
