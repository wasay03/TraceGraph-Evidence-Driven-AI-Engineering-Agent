from typing import Any


class AppError(Exception):
    """
    #Feature: Error taxonomy
    #Scenario: Base for every error the application raises deliberately
    #Complexity: Time O(1) - constant

    Carries an HTTP status, a stable machine code, a message and structured details.
    """

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """
        #Feature: Error taxonomy
        #Scenario: Construct an error with optional structured details
        #Complexity: Time O(1) - constant

        Args:
            message: Human readable description of the failure.
            details: Optional structured context.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BadRequestError(AppError):
    """
    #Feature: Error taxonomy
    #Scenario: Missing or invalid request parameters
    #Complexity: Time O(1) - constant
    """

    status_code = 400
    code = "bad_request"


class UnauthorizedError(AppError):
    """
    #Feature: Error taxonomy
    #Scenario: Missing or invalid credentials
    #Complexity: Time O(1) - constant
    """

    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    """
    #Feature: Error taxonomy
    #Scenario: Authenticated caller lacks a permission
    #Complexity: Time O(1) - constant
    """

    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    """
    #Feature: Error taxonomy
    #Scenario: Requested resource does not exist
    #Complexity: Time O(1) - constant
    """

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """
    #Feature: Error taxonomy
    #Scenario: Request conflicts with current resource state
    #Complexity: Time O(1) - constant
    """

    status_code = 409
    code = "conflict"


class InternalServerError(AppError):
    """
    #Feature: Error taxonomy
    #Scenario: Unexpected system failure
    #Complexity: Time O(1) - constant
    """

    status_code = 500
    code = "internal_error"


class DatabaseIntegrityError(AppError):
    """
    #Feature: Error taxonomy
    #Scenario: Database constraint or unique violation
    #Complexity: Time O(1) - constant
    """

    status_code = 409
    code = "db_integrity_error"


class DatabaseQueryError(AppError):
    """
    #Feature: Error taxonomy
    #Scenario: A stored function call failed for a non-integrity reason
    #Complexity: Time O(1) - constant
    """

    status_code = 500
    code = "db_query_error"


class DomainError(AppError):
    """
    #Feature: Error taxonomy
    #Scenario: Base for business rule violations
    #Complexity: Time O(1) - constant
    """

    status_code = 422
    code = "domain_error"


class UnknownTypeError(DomainError):
    """
    #Feature: Ontology validation
    #Scenario: A node or edge type is not registered
    #Complexity: Time O(1) - constant
    """

    code = "unknown_type"


class DomainViolationError(DomainError):
    """
    #Feature: Ontology validation
    #Scenario: Edge endpoints do not satisfy the edge signature
    #Complexity: Time O(1) - constant
    """

    code = "domain_violation"


class CardinalityViolationError(DomainError):
    """
    #Feature: Ontology validation
    #Scenario: Edge count exceeds the declared cardinality
    #Complexity: Time O(1) - constant
    """

    code = "cardinality_violation"


class MissingEvidenceError(DomainError):
    """
    #Feature: Ontology validation
    #Scenario: Edge written without the evidence its policy requires
    #Complexity: Time O(1) - constant
    """

    code = "missing_evidence"


class PropertyViolationError(DomainError):
    """
    #Feature: Ontology validation
    #Scenario: Node or edge property missing, unknown or of the wrong type
    #Complexity: Time O(1) - constant
    """

    code = "property_violation"


class TierViolationError(DomainError):
    """
    #Feature: Ontology validation
    #Scenario: Row written with an epistemic tier its type does not allow
    #Complexity: Time O(1) - constant
    """

    code = "tier_violation"


class QueryTypeError(DomainError):
    """
    #Feature: Reasoning engine
    #Scenario: Query IR fails type checking against the registry
    #Complexity: Time O(1) - constant
    """

    code = "query_type_error"


class ChangeSpecError(DomainError):
    """
    #Feature: Impact analysis
    #Scenario: ChangeSpec invalid or its target cannot be resolved unambiguously
    #Complexity: Time O(1) - constant
    """

    code = "changespec_error"


class ExtractionError(DomainError):
    """
    #Feature: Extraction pipeline
    #Scenario: An extraction pass failed on the repository
    #Complexity: Time O(1) - constant
    """

    code = "extraction_error"


class Errors:
    """
    #Feature: Error taxonomy
    #Scenario: Single namespace for raising structured errors, e.g. Errors.HTTP.NotFound
    #Complexity: Time O(1) - constant
    """

    class HTTP:
        """
        #Feature: Error taxonomy
        #Scenario: Transport level errors
        #Complexity: Time O(1) - constant
        """

        BadRequest = BadRequestError
        Unauthorized = UnauthorizedError
        Forbidden = ForbiddenError
        NotFound = NotFoundError
        Conflict = ConflictError
        InternalServerError = InternalServerError

    class Database:
        """
        #Feature: Error taxonomy
        #Scenario: Persistence errors
        #Complexity: Time O(1) - constant
        """

        IntegrityError = DatabaseIntegrityError
        QueryError = DatabaseQueryError

    class Domain:
        """
        #Feature: Error taxonomy
        #Scenario: Business rule violations
        #Complexity: Time O(1) - constant
        """

        Base = DomainError
        UnknownType = UnknownTypeError
        DomainViolation = DomainViolationError
        CardinalityViolation = CardinalityViolationError
        MissingEvidence = MissingEvidenceError
        PropertyViolation = PropertyViolationError
        TierViolation = TierViolationError
        QueryType = QueryTypeError
        ChangeSpec = ChangeSpecError
        Extraction = ExtractionError
