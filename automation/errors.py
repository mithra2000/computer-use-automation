from automation.models import Status


class AutomationError(Exception):
    code = "AUTOMATION_ERROR"
    status = Status.HARD_FAILURE

    def __init__(self, message: str, *, expected: str | None = None, observed: str | None = None):
        super().__init__(message)
        self.expected, self.observed = expected, observed


class TargetNotFoundError(AutomationError):
    code = "TARGET_NOT_FOUND"


class AmbiguousTargetError(AutomationError):
    code = "AMBIGUOUS_TARGET"
    status = Status.INTERVENTION_REQUIRED


class PolicyViolationError(AutomationError):
    code = "POLICY_BLOCKED"
    status = Status.POLICY_BLOCKED


class CheckpointError(AutomationError):
    code = "CHECKPOINT_FAILED"


class RecoveryExhaustedError(AutomationError):
    code = "RECOVERY_EXHAUSTED"


class SessionExpiredError(AutomationError):
    code = "SESSION_EXPIRED"
    status = Status.INTERVENTION_REQUIRED


class PermissionDeniedError(AutomationError):
    code = "PERMISSION_DENIED"


class BusinessOutcome(AutomationError):
    code = "member_not_found"
    status = Status.BUSINESS_OUTCOME


class ArtifactValidationError(AutomationError):
    code = "ARTIFACT_INVALID"


class CompatibilityError(AutomationError):
    code = "UNSUPPORTED_APP_VERSION"


class DiscoveryStoppedError(AutomationError):
    code = "DISCOVERY_STUCK"
    status = Status.INTERVENTION_REQUIRED
