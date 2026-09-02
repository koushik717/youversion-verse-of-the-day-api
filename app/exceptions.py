class ApiError(Exception):
    """
    Any error the API returns to a caller carries exactly these three things.
    One class, one place, so every error response — validation, upstream
    failure, whatever — comes back in the same JSON shape.
    """

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}
