from dataclasses import dataclass

from opengsync_db import SyncSession, models

from ...components import inputs
from ...core import exceptions as exc


@dataclass
class ProfileValues:
    institute: str | None = None
    department: str | None = None
    pi_name: str | None = None
    pi_email: str | None = None


class UserProfileMixin:
    """Organization (institute, department) and PI of a user, picked from the values other users have or typed new
    (core/column_values.py). Rendered with templates/forms/user-profile-fields.html.

    Requirements depend on the form and are checked by ``validate_profile``; the fields themselves are optional.
    """

    institute = inputs.column_value.ColumnValueInputField(
        "Institute",
        source="user_institute",
        required=False,
        new_label="New Institute",
        new_min_length=2,
        new_max_length=models.User.institute.type.length,
        placeholder="Search institutes or type a new one…",
    )
    department = inputs.column_value.ColumnValueInputField(
        "Department",
        source="user_department",
        required=False,
        new_label="New Department",
        new_min_length=2,
        new_max_length=models.User.department.type.length,
        placeholder="Search departments or type a new one…",
    )
    pi = inputs.column_value.ColumnValueInputField(
        "Principal Investigator",
        source="user_pi",
        required=False,
        new_label="New PI",
        new_min_length=3,
        new_max_length=models.User.pi_name.type.length,
        placeholder="Search PIs or type the name of a new one…",
    )
    # Only shown (and submitted) for a new PI
    pi_email = inputs.string.EmailInputField(
        "PI Email", required=False, max_length=models.User.pi_email.type.length, autocomplete="off",
    )

    def init_profile_fields(self, user: models.User | None = None, token: str | None = None) -> None:
        """Wire the fields (call after the form's ``__init__``); prefill from ``user``. ``token`` authorizes the
        searches on pages whose user is not logged in."""
        self.department.query_fields = {"institute": self.institute.id}
        if token:
            for field in (self.institute, self.department, self.pi):
                field.query_params = {"token": token}
        if user is not None:
            self.institute.set_values((user.institute,))
            self.department.set_values((user.department,))
            self.pi.set_values((user.pi_name, user.pi_email))

    def validate_profile(
        self, session: SyncSession, *, required: bool, keep: models.User | None = None,
    ) -> ProfileValues:
        """The values to store, new ones snapped to existing spellings. With ``required`` all must be given; with
        ``keep`` those already set on that user must not be cleared. Raises FormValidationException on errors."""
        institute = self.institute.resolve(session)
        department = self.department.resolve(
            session, filters={"institute": institute[0] if institute else None},
        )

        pi = None
        if self.pi.is_new:
            if not self.pi_email.data:
                self.pi_email.errors.append("Enter the email of the new PI.")
            else:
                pi = self.pi.resolve(session, new_extra=(str(self.pi_email.data),))
        else:
            pi = self.pi.resolve(session)

        values = ProfileValues(
            institute=institute[0] if institute else None,
            department=department[0] if department else None,
            pi_name=pi[0] if pi else None,
            pi_email=pi[1] if pi else None,
        )

        def require(field: inputs.BaseInputField, value: str | None, previous: str | None) -> None:
            if not value and not field.errors and (required or previous):
                field.errors.append(f"{field.label} is required.")

        require(self.institute, values.institute, keep.institute if keep else None)
        require(self.department, values.department, keep.department if keep else None)
        if not self.pi_email.errors:
            require(self.pi, values.pi_name, keep.pi_name if keep else None)

        if any(field.errors for field in (self.institute, self.department, self.pi, self.pi_email)):
            raise exc.FormValidationException(self)  # type: ignore[arg-type]
        return values

    @staticmethod
    def apply_profile(user: models.User, values: ProfileValues) -> None:
        user.institute = values.institute
        user.department = values.department
        user.pi_name = values.pi_name
        user.pi_email = values.pi_email
