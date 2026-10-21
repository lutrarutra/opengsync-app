from dataclasses import dataclass

from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class UserRoleEnum(DBEnum):
    label: str
    icon: str
    insider: bool = False


class UserRole(ExtendedEnum):
    label: str
    icon: str
    insider: bool
    DEACTIVATED = UserRoleEnum(0, "Deactivated", "🔒", False)
    ADMIN = UserRoleEnum(1, "Admin", "🤓", True)
    BIOINFORMATICIAN = UserRoleEnum(2, "Bioinformatician", "👨🏾‍💻", True)
    TECHNICIAN = UserRoleEnum(3, "Technician", "🧑🏽‍🔬", True)
    CLIENT = UserRoleEnum(4, "Client", "👶🏻", False)
    TEMPORARY = UserRoleEnum(5, "Temporary", "⏳", False)

    @classmethod
    def insiders(cls) -> list["UserRole"]:
        return [
            cls.ADMIN,
            cls.BIOINFORMATICIAN,
            cls.TECHNICIAN
        ]

    @classmethod
    def data_assigners(cls) -> list["UserRole"]:
        """Roles that add share paths to projects, requests, experiments and libraries."""
        return [cls.ADMIN, cls.BIOINFORMATICIAN]

    @classmethod
    def by_privilege(cls) -> list["UserRole"]:
        """Roles from least to most privileged."""
        return [cls.DEACTIVATED, cls.TEMPORARY, cls.CLIENT, cls.TECHNICIAN, cls.BIOINFORMATICIAN, cls.ADMIN]

    @property
    def privilege_rank(self) -> int:
        return UserRole.by_privilege().index(self)

    @property
    def select_name(self) -> str:
        return self.icon
    
    @property
    def display_name(self) -> str:
        return f"{self.label} {self.icon}"
